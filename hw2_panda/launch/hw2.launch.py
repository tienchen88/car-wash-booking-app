"""
Main HW2 launch file.

Starts:
  1. Ignition Gazebo  (hw2_world.sdf)
  2. robot_state_publisher  (panda_with_camera.urdf.xacro)
  3. ros_gz_bridge  (clock, TF, joint states, camera topics)
  4. ros2_control spawner  (joint_state_broadcaster, arm + hand controllers)
  5. MoveIt2 move_group
  6. color_detector node
  7. pick_and_place node  (optional, default on)

Launch argument:
  auto_start:=true/false  -- whether to run pick_and_place automatically
"""

import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess,
                             IncludeLaunchDescription, RegisterEventHandler,
                             TimerAction)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (Command, FindExecutable, LaunchConfiguration,
                                  PathJoinSubstitution)
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg = get_package_share_directory('hw2_panda')

    # ── Launch arguments ───────────────────────────────────────────────
    auto_start_arg = DeclareLaunchArgument(
        'auto_start', default_value='true',
        description='Auto-start pick_and_place node')

    auto_start = LaunchConfiguration('auto_start')

    # ── Robot description (xacro) ──────────────────────────────────────
    robot_description_content = Command([
        FindExecutable(name='xacro'), ' ',
        os.path.join(pkg, 'urdf', 'panda_with_camera.urdf.xacro'),
    ])
    robot_description = {'robot_description': robot_description_content}

    # ── Ignition Gazebo ───────────────────────────────────────────────
    world_file = os.path.join(pkg, 'worlds', 'hw2_world.sdf')
    ignition_gazebo = ExecuteProcess(
        cmd=['ign', 'gazebo', '-r', world_file],
        output='screen',
    )

    # ── robot_state_publisher ─────────────────────────────────────────
    robot_state_pub = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[robot_description, {'use_sim_time': True}],
    )

    # ── ros_gz_bridge ─────────────────────────────────────────────────
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock',
            '/tf@tf2_msgs/msg/TFMessage[ignition.msgs.Pose_V',
            '/joint_states@sensor_msgs/msg/JointState[ignition.msgs.Model',
            '/camera/image_raw@sensor_msgs/msg/Image[ignition.msgs.Image',
            '/camera/camera_info@sensor_msgs/msg/CameraInfo[ignition.msgs.CameraInfo',
        ],
        output='screen',
        parameters=[{'use_sim_time': True}],
    )

    # ── ros2_control node ─────────────────────────────────────────────
    ros2_control_node = Node(
        package='controller_manager',
        executable='ros2_control_node',
        parameters=[
            robot_description,
            os.path.join(pkg, 'config', 'controllers.yaml'),
            {'use_sim_time': True},
        ],
        output='screen',
    )

    # ── Spawn controllers (sequential after ros2_control starts) ──────
    joint_state_broadcaster_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['joint_state_broadcaster', '--controller-manager', '/controller_manager'],
        output='screen',
    )

    arm_controller_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['panda_arm_controller', '--controller-manager', '/controller_manager'],
        output='screen',
    )

    hand_controller_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=['panda_hand_controller', '--controller-manager', '/controller_manager'],
        output='screen',
    )

    # Spawn arm controller only after joint_state_broadcaster is active
    arm_controller_event = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[arm_controller_spawner],
        )
    )
    hand_controller_event = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=arm_controller_spawner,
            on_exit=[hand_controller_spawner],
        )
    )

    # ── MoveIt2 move_group ────────────────────────────────────────────
    moveit_config = {
        'robot_description': robot_description_content,
        'robot_description_semantic': open(
            os.path.join(pkg, 'config', 'panda.srdf')).read(),
        'robot_description_kinematics': os.path.join(pkg, 'config', 'kinematics.yaml'),
        'robot_description_planning': os.path.join(pkg, 'config', 'joint_limits.yaml'),
        'planning_pipelines': ['ompl'],
        'ompl': os.path.join(pkg, 'config', 'ompl_planning.yaml'),
        'use_sim_time': True,
        'publish_robot_description_semantic': True,
    }

    move_group_node = Node(
        package='moveit_ros_move_group',
        executable='move_group',
        output='screen',
        parameters=[moveit_config],
    )

    # ── Vision node ───────────────────────────────────────────────────
    color_detector = Node(
        package='hw2_panda',
        executable='color_detector.py',
        name='color_detector',
        output='screen',
        parameters=[{'use_sim_time': True}],
    )

    # ── Pick-and-place node (delayed start to let everything settle) ──
    pick_and_place = TimerAction(
        period=10.0,
        actions=[
            Node(
                package='hw2_panda',
                executable='pick_and_place.py',
                name='pick_and_place',
                output='screen',
                parameters=[{'use_sim_time': True}],
                condition=IfCondition(auto_start),
            )
        ],
    )

    return LaunchDescription([
        auto_start_arg,
        ignition_gazebo,
        robot_state_pub,
        bridge,
        ros2_control_node,
        joint_state_broadcaster_spawner,
        arm_controller_event,
        hand_controller_event,
        move_group_node,
        color_detector,
        pick_and_place,
    ])
