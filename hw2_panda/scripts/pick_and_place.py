#!/usr/bin/env python3
"""
Pick-and-place node using MoveIt2 (moveit_py).

State machine:
  INIT → SCAN → PICK_RED → PLACE_RED → PICK_GREEN → PLACE_GREEN → DONE

Subscribes:
  /detected_cubes  (geometry_msgs/PoseArray)
    poses[0] = red cube world pose
    poses[1] = green cube world pose

Actions used (via moveit_py):
  /move_action             -- arm motion planning
  /panda_hand_controller/gripper_action  -- gripper open/close
"""

import math
import time
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

from geometry_msgs.msg import Pose, PoseArray, PoseStamped
from control_msgs.action import GripperCommand
from moveit.planning import MoveItPy
from moveit.core.robot_state import RobotState
import numpy as np
from scipy.spatial.transform import Rotation as R


# ─── Tunable parameters ────────────────────────────────────────────────────
APPROACH_HEIGHT   = 0.15   # metres above target before descending
PLACE_HEIGHT      = 0.02   # metres above bucket rim when releasing
SCAN_JOINTS = {            # joint-space pose so camera faces the table
    'panda_joint1': 0.0,
    'panda_joint2': 0.0,
    'panda_joint3': 0.0,
    'panda_joint4': -1.57,
    'panda_joint5': 0.0,
    'panda_joint6':  1.57,
    'panda_joint7':  0.785,
}

# Bucket centres in world frame (must match hw2_world.sdf)
RED_BUCKET_POS   = (0.7,  0.28, 0.75 + 0.12 + PLACE_HEIGHT)   # bucket top + offset
GREEN_BUCKET_POS = (0.7, -0.28, 0.75 + 0.12 + PLACE_HEIGHT)

GRIPPER_OPEN   = 0.04   # metres (max stroke per finger)
GRIPPER_CLOSED = 0.003  # slightly open so it doesn't crush (Gazebo sim)

DETECTION_TIMEOUT = 10.0   # seconds to wait for cube detection
PLAN_ATTEMPTS     = 3
# ───────────────────────────────────────────────────────────────────────────


def _pose_above(pos, height_offset: float, yaw: float = 0.0) -> Pose:
    """Return a Pose directly above pos with gripper pointing down."""
    p = Pose()
    p.position.x = pos[0]
    p.position.y = pos[1]
    p.position.z = pos[2] + height_offset
    # Gripper pointing straight down: rotate 180° around X from identity
    q = R.from_euler('xyz', [math.pi, 0.0, yaw]).as_quat()  # xyzw
    p.orientation.x = q[0]
    p.orientation.y = q[1]
    p.orientation.z = q[2]
    p.orientation.w = q[3]
    return p


class PickAndPlace(Node):
    def __init__(self):
        super().__init__('pick_and_place')

        self.moveit = MoveItPy(node_name='pick_and_place_moveit')
        self.arm = self.moveit.get_planning_component('panda_arm')
        self.robot_model = self.moveit.get_robot_model()

        self.gripper_client = ActionClient(
            self, GripperCommand,
            '/panda_hand_controller/gripper_action')

        self.detected_cubes: PoseArray | None = None
        self.sub = self.create_subscription(
            PoseArray, '/detected_cubes', self._cb_cubes, 1)

        self.get_logger().info('PickAndPlace node ready')

    # ── Callbacks ────────────────────────────────────────────────────────
    def _cb_cubes(self, msg: PoseArray):
        self.detected_cubes = msg

    # ── Gripper helpers ──────────────────────────────────────────────────
    def _move_gripper(self, position: float, max_effort: float = 50.0):
        goal = GripperCommand.Goal()
        goal.command.position = position
        goal.command.max_effort = max_effort
        self.gripper_client.wait_for_server(timeout_sec=5.0)
        future = self.gripper_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        result_future = future.result().get_result_async()
        rclpy.spin_until_future_complete(self, result_future, timeout_sec=5.0)

    def open_gripper(self):
        self.get_logger().info('Gripper: OPEN')
        self._move_gripper(GRIPPER_OPEN)

    def close_gripper(self):
        self.get_logger().info('Gripper: CLOSE')
        self._move_gripper(GRIPPER_CLOSED, max_effort=30.0)

    # ── Arm motion helpers ───────────────────────────────────────────────
    def _move_to_joints(self, joint_values: dict) -> bool:
        robot_state = RobotState(self.robot_model)
        for joint, val in joint_values.items():
            robot_state.set_joint_positions({joint: val})
        self.arm.set_goal_state(robot_state=robot_state)
        return self._plan_and_execute()

    def _move_to_pose(self, pose: Pose, frame_id: str = 'world') -> bool:
        ps = PoseStamped()
        ps.header.frame_id = frame_id
        ps.header.stamp = self.get_clock().now().to_msg()
        ps.pose = pose
        self.arm.set_goal_state(
            pose_stamped_msg=ps, pose_link='panda_hand')
        return self._plan_and_execute()

    def _plan_and_execute(self) -> bool:
        for attempt in range(1, PLAN_ATTEMPTS + 1):
            plan_result = self.arm.plan()
            if plan_result:
                self.get_logger().info(
                    f'Plan found (attempt {attempt}), executing...')
                robot_trajectory = plan_result.trajectory
                self.moveit.execute(robot_trajectory, blocking=True,
                                    controllers=['panda_arm_controller'])
                return True
            self.get_logger().warn(f'Planning failed (attempt {attempt})')
        self.get_logger().error('All planning attempts failed')
        return False

    # ── Detection helpers ─────────────────────────────────────────────────
    def _wait_for_detection(self, colour: str) -> Pose | None:
        """
        Move to scan pose then wait until the desired colour is detected.
        colour: 'red' (index 0) or 'green' (index 1)
        """
        idx = 0 if colour == 'red' else 1
        self.get_logger().info(f'Moving to scan pose to detect {colour} cube...')
        self._move_to_joints(SCAN_JOINTS)

        self.detected_cubes = None
        deadline = time.time() + DETECTION_TIMEOUT
        while rclpy.ok() and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if (self.detected_cubes is not None and
                    len(self.detected_cubes.poses) > idx):
                pose = self.detected_cubes.poses[idx]
                self.get_logger().info(
                    f'{colour} cube detected at '
                    f'({pose.position.x:.3f}, {pose.position.y:.3f}, '
                    f'{pose.position.z:.3f})')
                return pose
        self.get_logger().error(f'Timeout: {colour} cube not detected')
        return None

    # ── Pick / Place ──────────────────────────────────────────────────────
    def pick(self, cube_pose: Pose) -> bool:
        pos = (cube_pose.position.x,
               cube_pose.position.y,
               cube_pose.position.z)

        self.open_gripper()

        # Pre-grasp: above cube
        if not self._move_to_pose(_pose_above(pos, APPROACH_HEIGHT)):
            return False

        # Descend to grasp height
        grasp_pose = _pose_above(pos, 0.0)
        if not self._move_to_pose(grasp_pose):
            return False

        self.close_gripper()

        # Lift
        if not self._move_to_pose(_pose_above(pos, APPROACH_HEIGHT)):
            return False

        return True

    def place(self, bucket_pos: tuple) -> bool:
        # Pre-place: above bucket
        if not self._move_to_pose(_pose_above(bucket_pos, APPROACH_HEIGHT)):
            return False

        # Lower to place height (already baked into bucket_pos z)
        if not self._move_to_pose(_pose_above(bucket_pos, 0.0)):
            return False

        self.open_gripper()
        time.sleep(0.5)

        # Retreat upward
        if not self._move_to_pose(_pose_above(bucket_pos, APPROACH_HEIGHT)):
            return False

        return True

    # ── Main task ─────────────────────────────────────────────────────────
    def run(self):
        self.get_logger().info('=== HW2 Pick-and-Place task START ===')

        # --- Red cube ---
        red_pose = self._wait_for_detection('red')
        if red_pose is None:
            return
        if not self.pick(red_pose):
            self.get_logger().error('Failed to pick red cube')
            return
        if not self.place(RED_BUCKET_POS):
            self.get_logger().error('Failed to place red cube')
            return
        self.get_logger().info('Red cube placed successfully ✓')

        # --- Green cube ---
        green_pose = self._wait_for_detection('green')
        if green_pose is None:
            return
        if not self.pick(green_pose):
            self.get_logger().error('Failed to pick green cube')
            return
        if not self.place(GREEN_BUCKET_POS):
            self.get_logger().error('Failed to place green cube')
            return
        self.get_logger().info('Green cube placed successfully ✓')

        self.get_logger().info('=== HW2 Pick-and-Place task COMPLETE ===')


def main(args=None):
    rclpy.init(args=args)
    node = PickAndPlace()
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
