"""
HW2 launch file — Gz Harmonic (ROS2 Jazzy).

Starts:
  1. gz sim  (hw2_world.sdf  — includes Panda SDF model + overhead camera)
  2. robot_state_publisher  (URDF from moveit_resources_panda_description)
  3. ros_gz_bridge  (clock, joint states, camera)
  4. static_transform_publisher  (overhead camera → world TF)
  5. MoveIt2 move_group
  6. color_detector node
  7. pick_and_place node  (optional, default on)
"""

import os
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess,
                             TimerAction)
from launch.conditions import IfCondition
from launch.substitutions import (Command, FindExecutable, LaunchConfiguration)
from launch_ros.actions import Node


def _load_yaml(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


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
    ros2_ws_src = os.path.expanduser('~/ros2_ws/src')
    gz_env = dict(os.environ)
    existing = gz_env.get('GZ_SIM_RESOURCE_PATH', '')
    gz_env['GZ_SIM_RESOURCE_PATH'] = (
        ros2_ws_src + ((':' + existing) if existing else ''))
    # WSL2: force software rendering to avoid D3D12/OpenGL crash
    gz_env['LIBGL_ALWAYS_SOFTWARE'] = '1'

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
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
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

    # ── Static TF for overhead camera ─────────────────────────────────
    # Camera in hw2_world.sdf: pose="0.5 0 2.25 0 1.5708 0" (pitch=90° → down)
    # static_transform_publisher args order: x y z yaw pitch roll parent child
    overhead_camera_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='overhead_camera_tf',
        arguments=['0.5', '0', '2.25', '0', '1.5708', '0',
                   'world', 'camera_optical_link'],
        parameters=[{'use_sim_time': True}],
    )

    # ── MoveIt2 move_group ────────────────────────────────────────────
    # Load YAML configs as dicts so ROS2 creates proper nested parameters.
    kinematics_cfg = _load_yaml(os.path.join(pkg, 'config', 'kinematics.yaml'))
    ompl_cfg = _load_yaml(os.path.join(pkg, 'config', 'ompl_planning.yaml'))
    # ompl_cfg has top-level key 'ompl', so params become ompl.planning_plugin etc.

    moveit_config = {
        'robot_description': robot_description_content,
        'robot_description_semantic': open(
            os.path.join(pkg, 'config', 'panda.srdf')).read(),
        'use_sim_time': True,
        'publish_robot_description_semantic': True,
        'planning_pipelines': ['ompl'],
    }

    move_group_node = Node(
        package='moveit_ros_move_group',
        executable='move_group',
        output='screen',
        parameters=[
            moveit_config,
            {'robot_description_kinematics': kinematics_cfg},
            ompl_cfg,
        ],
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
        overhead_camera_tf,
        move_group_node,
        color_detector,
        pick_and_place,
    ])
