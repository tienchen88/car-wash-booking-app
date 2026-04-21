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
import tf2_ros
import tf2_geometry_msgs  # noqa: F401 — registers PoseStamped transform support
from geometry_msgs.msg import PoseStamped, Point


# HSV thresholds for Ignition Gazebo rendered colors
# Red wraps around H=0/180
RED_LOWER1 = np.array([0,   120,  80])
RED_UPPER1 = np.array([10,  255, 255])
RED_LOWER2 = np.array([165, 120,  80])
RED_UPPER2 = np.array([180, 255, 255])

# Green
GREEN_LOWER = np.array([40,  80,  60])
GREEN_UPPER = np.array([85, 255, 255])

# Minimum contour area (pixels²) to consider a valid cube detection
MIN_CONTOUR_AREA = 300

# Known table surface height in world frame (metres)
# Cube centre = table top + half cube side = 0.75 + 0.025
TABLE_Z = 0.75
CUBE_HALF_HEIGHT = 0.025
CUBE_CENTRE_Z = TABLE_Z + CUBE_HALF_HEIGHT


class ColorDetector(Node):
    def __init__(self):
        super().__init__('color_detector')

        self.bridge = CvBridge()
        self.camera_info: CameraInfo | None = None

        # TF buffer for camera → world transform
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

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

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)
        green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_OPEN, kernel)

        red_pose = self._mask_to_world_pose(
            red_mask, msg.header, label='red')
        green_pose = self._mask_to_world_pose(
            green_mask, msg.header, label='green')

        # Publish results
        out = PoseArray()
        out.header.stamp = msg.header.stamp
        out.header.frame_id = 'world'
        if red_pose is not None:
            out.poses.append(red_pose)
        if green_pose is not None:
            out.poses.append(green_pose)
        self.pub_cubes.publish(out)

        # Debug overlay
        debug = bgr.copy()
        debug[red_mask > 0] = (0, 0, 200)
        debug[green_mask > 0] = (0, 200, 0)
        self.pub_debug.publish(
            self.bridge.cv2_to_imgmsg(debug, encoding='bgr8'))

    def _mask_to_world_pose(self, mask, header, label: str) -> Pose | None:
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

        # Back-project pixel (u,v) to a 3-D ray in camera optical frame
        fx = self.camera_info.k[0]
        fy = self.camera_info.k[4]
        cx = self.camera_info.k[2]
        cy = self.camera_info.k[5]

        # Normalised ray direction in camera_optical frame
        ray = np.array([(u - cx) / fx, (v - cy) / fy, 1.0])

        # Build a unit-depth point on the ray and transform to world frame
        # so we can solve for the intersection with the known Z plane
        cam_point = PoseStamped()
        cam_point.header = header
        cam_point.header.frame_id = 'camera_optical_link'
        cam_point.pose.position.x = float(ray[0])
        cam_point.pose.position.y = float(ray[1])
        cam_point.pose.position.z = float(ray[2])
        cam_point.pose.orientation.w = 1.0

        # Origin of camera in world frame
        cam_origin = PoseStamped()
        cam_origin.header = header
        cam_origin.header.frame_id = 'camera_optical_link'
        cam_origin.pose.orientation.w = 1.0

        try:
            world_ray_end = self.tf_buffer.transform(
                cam_point, 'world', timeout=rclpy.duration.Duration(seconds=0.1))
            world_origin = self.tf_buffer.transform(
                cam_origin, 'world', timeout=rclpy.duration.Duration(seconds=0.1))
        except Exception as e:
            self.get_logger().warn(
                f'TF lookup failed for {label}: {e}', throttle_duration_sec=2.0)
            return None

        ox = world_origin.pose.position.x
        oy = world_origin.pose.position.y
        oz = world_origin.pose.position.z
        dx = world_ray_end.pose.position.x - ox
        dy = world_ray_end.pose.position.y - oy
        dz = world_ray_end.pose.position.z - oz

        if abs(dz) < 1e-6:
            self.get_logger().warn(
                f'Ray parallel to table for {label}', throttle_duration_sec=2.0)
            return None

        # Solve for t where oz + t*dz == CUBE_CENTRE_Z
        t = (CUBE_CENTRE_Z - oz) / dz
        if t < 0:
            return None

        wx = ox + t * dx
        wy = oy + t * dy
        wz = CUBE_CENTRE_Z

        self.get_logger().info(
            f'[{label}] detected at world ({wx:.3f}, {wy:.3f}, {wz:.3f})',
            throttle_duration_sec=1.0)

        pose = Pose()
        pose.position.x = wx
        pose.position.y = wy
        pose.position.z = wz
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
