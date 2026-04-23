#!/usr/bin/env python3
"""
Color detector node: subscribes to RGB camera, detects red/green cubes via
HSV filtering, and publishes their 3D world positions as a PoseArray.

Topic subscriptions:
  /camera/image_raw        (sensor_msgs/Image)
  /camera/camera_info      (sensor_msgs/CameraInfo)

Topic publications:
  /detected_cubes          (geometry_msgs/PoseArray)
    - poses[0]: red cube world pose   (if detected)
    - poses[1]: green cube world pose (if detected)
  /camera/debug_image      (sensor_msgs/Image)  -- color masks overlay
"""

import rclpy
from rclpy.node import Node
import numpy as np
import cv2
from cv_bridge import CvBridge

from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PoseArray, Pose


# HSV thresholds for Ignition Gazebo rendered colors
RED_LOWER1 = np.array([0,   120,  80])
RED_UPPER1 = np.array([10,  255, 255])
RED_LOWER2 = np.array([165, 120,  80])
RED_UPPER2 = np.array([180, 255, 255])

GREEN_LOWER = np.array([40,  80,  60])
GREEN_UPPER = np.array([85, 255, 255])

MIN_CONTOUR_AREA = 300

TABLE_Z        = 0.75
CUBE_HALF_HEIGHT = 0.025
CUBE_CENTRE_Z  = TABLE_Z + CUBE_HALF_HEIGHT   # 0.775 m

# ── Known overhead-camera world pose (must match hw2_world.sdf) ──────────────
# <pose>0.5 0 2.25 0 1.5708 0</pose>
CAM_POS = np.array([0.5, 0.0, 2.25])

# Rotation matrix R: camera-optical frame → world frame.
# Gazebo cameras capture images along the +X axis of their link frame.
# After pitch=π/2 (Ry(π/2)), link +X → world -Z  (looking straight down).
# "right" in image = link -Y → world -Y after rotation.
# "down"  in image = link -Z → world +X after rotation.
#
# So:  optical-X (right) → world -Y
#      optical-Y (down)  → world +X  ← NOTE: +X not -X
#      optical-Z (depth) → world -Z
#
# R columns = camera axes expressed in world:
#   col-0 = world direction of optical-X = (0, -1,  0)
#   col-1 = world direction of optical-Y = (1,  0,  0)
#   col-2 = world direction of optical-Z = (0,  0, -1)
CAM_R = np.array([
    [ 0, 1, 0],
    [-1, 0, 0],
    [ 0, 0,-1],
], dtype=float)
# ─────────────────────────────────────────────────────────────────────────────


class ColorDetector(Node):
    def __init__(self):
        super().__init__('color_detector')

        self.bridge = CvBridge()
        self.camera_info: CameraInfo | None = None

        self.sub_info = self.create_subscription(
            CameraInfo, '/camera/camera_info', self._cb_info, 1)
        self.sub_img = self.create_subscription(
            Image, '/camera/image_raw', self._cb_image, 1)

        self.pub_cubes = self.create_publisher(PoseArray, '/detected_cubes', 1)
        self.pub_debug = self.create_publisher(Image, '/camera/debug_image', 1)

        self.get_logger().info('ColorDetector ready — waiting for camera...')

    def _cb_info(self, msg: CameraInfo):
        self.camera_info = msg

    def _cb_image(self, msg: Image):
        if self.camera_info is None:
            return

        bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

        red_mask = (cv2.inRange(hsv, RED_LOWER1, RED_UPPER1) |
                    cv2.inRange(hsv, RED_LOWER2, RED_UPPER2))
        green_mask = cv2.inRange(hsv, GREEN_LOWER, GREEN_UPPER)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        red_mask   = cv2.morphologyEx(red_mask,   cv2.MORPH_OPEN, kernel)
        green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_OPEN, kernel)

        red_pose   = self._mask_to_world_pose(red_mask,   label='red')
        green_pose = self._mask_to_world_pose(green_mask, label='green')

        out = PoseArray()
        out.header.stamp    = msg.header.stamp
        out.header.frame_id = 'world'
        if red_pose   is not None:
            out.poses.append(red_pose)
        if green_pose is not None:
            out.poses.append(green_pose)
        self.pub_cubes.publish(out)

        debug = bgr.copy()
        debug[red_mask   > 0] = (0,   0, 200)
        debug[green_mask > 0] = (0, 200,   0)
        self.pub_debug.publish(
            self.bridge.cv2_to_imgmsg(debug, encoding='bgr8'))

    def _mask_to_world_pose(self, mask, label: str) -> Pose | None:
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) < MIN_CONTOUR_AREA:
            return None

        M = cv2.moments(largest)
        if M['m00'] == 0:
            return None
        u = M['m10'] / M['m00']
        v = M['m01'] / M['m00']

        fx = self.camera_info.k[0]
        fy = self.camera_info.k[4]
        cx = self.camera_info.k[2]
        cy = self.camera_info.k[5]

        # Ray in camera optical frame (Z=1 unit depth)
        ray_cam = np.array([(u - cx) / fx, (v - cy) / fy, 1.0])

        # Transform ray to world frame using known camera extrinsics
        ray_world = CAM_R @ ray_cam

        dz = ray_world[2]
        if abs(dz) < 1e-6 or dz > 0:   # ray must travel downward
            return None

        t = (CUBE_CENTRE_Z - CAM_POS[2]) / dz
        if t < 0:
            return None

        world_pt = CAM_POS + t * ray_world

        self.get_logger().info(
            f'[{label}] pixel ({u:.0f},{v:.0f}) → '
            f'world ({world_pt[0]:.3f}, {world_pt[1]:.3f}, {CUBE_CENTRE_Z:.3f})',
            throttle_duration_sec=1.0)

        pose = Pose()
        pose.position.x = float(world_pt[0])
        pose.position.y = float(world_pt[1])
        pose.position.z = CUBE_CENTRE_Z
        pose.orientation.w = 1.0
        return pose


def main(args=None):
    rclpy.init(args=args)
    node = ColorDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
