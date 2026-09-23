"""Rocket League packet -> the plain-text state the Open-Jev payload was validated with.

Pure functions: no RLBot import, so this is testable without the game running.
Unreal units are centimetres; the model reads metres, km/h and degrees.
"""
import math

UU_TO_M = 0.01
UUS_TO_KPH = 0.036        # 1 uu/s = 0.01 m/s = 0.036 km/h
SUPERSONIC_KPH = 2200.0


def signed_angle_to_deg(car_x, car_y, car_yaw, target_x, target_y):
    """Angle from the car nose to a point: negative is left, positive is right.

    Rocket League yaw increases counter-clockwise, so a target counter-clockwise
    of the nose is to the car's left and must come back negative.
    """
    bearing = math.atan2(target_y - car_y, target_x - car_x)
    offset = math.degrees(bearing - car_yaw)
    return -((offset + 180.0) % 360.0 - 180.0)


def describe_angle(degrees, dead_zone=5.0):
    """Render the angle the way the validated state text words it.

    Below the dead zone the model reliably answers `left` for a 2 deg reading,
    so the caller states 'straight ahead' rather than trusting that decision.
    """
    magnitude = abs(degrees)
    if magnitude < dead_zone:
        return "0 deg straight ahead"
    return f"{magnitude:.0f} deg to the {'right' if degrees > 0 else 'left'}"


def seconds_to_contact(distance_m, car_speed_kph, floor=0.05):
    if car_speed_kph <= 1.0:
        return 9.9
    return max(floor, distance_m / (car_speed_kph / 3.6))


def build_state(*, car_pos, car_yaw, car_speed_uus, car_boost, car_on_ground,
                has_flip, ball_pos, opponent_goal_pos, shot_lane_open, is_last_defender):
    """Return the exact sentence format measured at 6/7 on the steer sweep."""
    cx, cy, _ = car_pos
    bx, by, bz = ball_pos
    distance_m = math.dist((cx, cy), (bx, by)) * UU_TO_M
    speed_kph = car_speed_uus * UUS_TO_KPH
    angle = signed_angle_to_deg(cx, cy, car_yaw, bx, by)
    goal_m = math.dist((cx, cy), opponent_goal_pos[:2]) * UU_TO_M
    ground = "on ground" if car_on_ground else "in the air"
    flip = "flip ready" if has_flip else "no flip"
    return (
        f"Ball {distance_m:.1f} m away, {describe_angle(angle)}, {bz * UU_TO_M:.1f} m high, "
        f"{seconds_to_contact(distance_m, speed_kph):.2f} s to contact. "
        f"Car at {speed_kph:.0f} kph with {car_boost:.0f} boost, {ground}, {flip}. "
        f"Opponent goal {goal_m:.1f} m ahead, "
        f"{'shot lane open' if shot_lane_open else 'shot lane blocked'}. "
        f"Car is {'last defender' if is_last_defender else 'not last defender'}."
    )
