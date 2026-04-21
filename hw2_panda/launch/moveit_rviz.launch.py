"""
Standalone MoveIt2 + RViz launch for manual testing (no Gazebo).
Run this separately from a terminal to interact with the planning scene.
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch.substitutions import Command, FindExecutable
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory('hw2_panda')

    robot_description_content = Command([
        FindExecutable(name='xacro'), ' ',
        os.path.join(pkg, 'urdf', 'panda_with_camera.urdf.xacro'),
    ])

    moveit_config = {
        'robot_description': robot_description_content,
        'robot_description_semantic': open(
            os.path.join(pkg, 'config', 'panda.srdf')).read(),
        'robot_description_kinematics': os.path.join(pkg, 'config', 'kinematics.yaml'),
        'planning_pipelines': ['ompl'],
        'ompl': os.path.join(pkg, 'config', 'ompl_planning.yaml'),
        'publish_robot_description_semantic': True,
    }

    move_group = Node(
        package='moveit_ros_move_group',
        executable='move_group',
        output='screen',
        parameters=[moveit_config],
    )

    rviz_config = os.path.join(pkg, 'rviz', 'hw2.rviz')
    rviz = Node(
        package='rviz2',
        executable='rviz2',
        arguments=['-d', rviz_config] if os.path.exists(rviz_config) else [],
        parameters=[moveit_config],
        output='screen',
    )

    robot_state_pub = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[{'robot_description': robot_description_content}],
    )

    joint_state_pub = Node(
        package='joint_state_publisher_gui',
        executable='joint_state_publisher_gui',
    )

    return LaunchDescription([
        robot_state_pub,
        joint_state_pub,
        move_group,
        rviz,
    ])
