"""
HW2 launch file — Gz Harmonic (ROS2 Jazzy).

Starts:
  1. gz sim  (hw2_world.sdf  — includes Panda SDF model + overhead camera)
  2. robot_state_publisher  (URDF from moveit_resources_panda_description)
  3. ros_gz_bridge  (clock, joint states, camera)
  4. MoveIt2 move_group
  5. color_detector node
  6. pick_and_place node  (optional, default on)
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess,
                             TimerAction)
from launch.conditions import IfCondition
from launch.substitutions import (Command, FindExecutable, LaunchConfiguration)
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory('hw2_panda')
    panda_desc_pkg = get_package_share_directory(
        'moveit_resources_panda_description')

    # ── Launch arguments ───────────────────────────────────────────────
    auto_start_arg = DeclareLaunchArgument(
        'auto_start', default_value='true',
        description='Auto-start pick_and_place node')
    auto_start = LaunchConfiguration('auto_start')

    # ── Robot description (URDF from moveit_resources_panda_description) ─
    robot_description_content = Command([
        FindExecutable(name='xacro'), ' ',
        os.path.join(panda_desc_pkg, 'urdf', 'panda.urdf.xacro'),
    ])
    robot_description = {'robot_description': robot_description_content}

    # ── Gz Sim ────────────────────────────────────────────────────────
    world_file = os.path.join(pkg, 'worlds', 'hw2_world.sdf')
    # GZ_SIM_RESOURCE_PATH lets Gazebo find the Panda model folder
    ros2_ws_src = os.path.expanduser('~/ros2_ws/src')
    gz_env = dict(os.environ)
    existing = gz_env.get('GZ_SIM_RESOURCE_PATH', '')
    gz_env['GZ_SIM_RESOURCE_PATH'] = (
        ros2_ws_src + ((':' + existing) if existing else ''))

    gz_sim = ExecuteProcess(
        cmd=['gz', 'sim', '-r', world_file],
        output='screen',
        additional_env=gz_env,
    )

    # ── robot_state_publisher ─────────────────────────────────────────
    robot_state_pub = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[robot_description, {'use_sim_time': True}],
    )

    # ── ros_gz_bridge ─────────────────────────────────────────────────
    # Gz Harmonic uses gz.msgs (not ignition.msgs)
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            # Joint states: Gz publishes at this topic for SDF models
            '/world/hw2_world/model/Panda/joint_state'
            '@sensor_msgs/msg/JointState[gz.msgs.Model',
            '/camera/image_raw@sensor_msgs/msg/Image[gz.msgs.Image',
            '/camera/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo',
        ],
        output='screen',
        parameters=[{'use_sim_time': True}],
        remappings=[
            ('/world/hw2_world/model/Panda/joint_state', '/joint_states'),
        ],
    )

    # ── MoveIt2 move_group ────────────────────────────────────────────
    moveit_config = {
        'robot_description': robot_description_content,
        'robot_description_semantic': open(
            os.path.join(pkg, 'config', 'panda.srdf')).read(),
        'robot_description_kinematics':
            os.path.join(pkg, 'config', 'kinematics.yaml'),
        'robot_description_planning':
            os.path.join(pkg, 'config', 'joint_limits.yaml'),
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

    # ── Pick-and-place (delayed 12 s to let Gz + MoveIt2 settle) ─────
    pick_and_place = TimerAction(
        period=12.0,
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
        gz_sim,
        robot_state_pub,
        bridge,
        move_group_node,
        color_detector,
        pick_and_place,
    ])
