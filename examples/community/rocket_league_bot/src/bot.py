"""RLBot v5 agent: the model decides steer/boost off-thread, heuristics do the rest.

Validation behind this split (measured against the released 2B checkpoint):
  steer    6/7 on a direction sweep, 0.82 correct vs 0.06 wrong  -> model
  boost    monotonic in boost remaining but never crosses 0.5    -> model, threshold 0.35
  throttle flips only when the state text already says "reverse" -> heuristic
  jump     0.196..0.220 across ball heights 0.1 m to 5 m         -> heuristic

Written against the RLBot v5 API (rlbot.managers.Bot, rlbot.flat.ControllerState).
Two field names are marked VERIFY: they were not confirmed against a running game.
"""
import math

from rlbot.flat import ControllerState, GamePacket
from rlbot.managers import Bot

from client import JevController
from state import UU_TO_M, UUS_TO_KPH, build_state, signed_angle_to_deg

STEER_VALUES = {"left": -1.0, "straight": 0.0, "right": 1.0}
DEAD_ZONE_DEG = 5.0        # The model answers `left` at 2 deg; below this, go straight.
REVERSE_ANGLE_DEG = 110.0
JUMP_HEIGHT_M = 1.5
JUMP_CONTACT_S = 0.3
SUPERSONIC_KPH = 2200.0
BLUE_GOAL = (0.0, -5120.0)
ORANGE_GOAL = (0.0, 5120.0)


class JevBot(Bot):
    def initialize(self):
        self.jev = JevController()   # host/port from JEV_HOST / JEV_PORT
        self.logger.info("Open-Jev controller started")

    def get_output(self, packet: GamePacket) -> ControllerState:
        if not packet.players or not packet.balls:
            return ControllerState()
        me = packet.players[self.index]
        physics = me.physics
        ball = packet.balls[0].physics.location

        car_xy = (physics.location.x, physics.location.y)
        yaw = physics.rotation.yaw
        velocity = physics.velocity
        speed_uus = math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2)
        speed_kph = speed_uus * UUS_TO_KPH
        angle = signed_angle_to_deg(car_xy[0], car_xy[1], yaw, ball.x, ball.y)
        distance_m = math.dist(car_xy, (ball.x, ball.y)) * UU_TO_M
        goal = ORANGE_GOAL if me.team == 0 else BLUE_GOAL

        # VERIFY these two against your build; print(dir(me)) once if a name is wrong.
        boost = getattr(me, "boost", 33)
        on_ground = getattr(physics, "has_wheel_contact", getattr(me, "has_wheel_contact", True))

        # Hand over the newest scene and take whatever answer exists. Neither call
        # blocks: a state superseded before it is sent is dropped, never queued.
        self.jev.submit(build_state(
            car_pos=(car_xy[0], car_xy[1], physics.location.z), car_yaw=yaw,
            car_speed_uus=speed_uus, car_boost=boost, car_on_ground=on_ground,
            has_flip=on_ground, ball_pos=(ball.x, ball.y, ball.z),
            opponent_goal_pos=goal, shot_lane_open=True, is_last_defender=True))
        decision = self.jev.decision()

        reversing = abs(angle) > REVERSE_ANGLE_DEG
        steer = 0.0 if abs(angle) < DEAD_ZONE_DEG else STEER_VALUES[decision["steer"]]
        seconds = distance_m / max(speed_kph / 3.6, 1.0)
        return ControllerState(
            steer=-steer if reversing else steer,   # A reversing car steers mirrored.
            throttle=-1.0 if reversing else 1.0,
            boost=decision["boost"] and on_ground and speed_kph < SUPERSONIC_KPH,
            jump=(ball.z * UU_TO_M > JUMP_HEIGHT_M and seconds < JUMP_CONTACT_S and on_ground),
        )

    def retire(self):
        self.jev.close()


if __name__ == "__main__":
    JevBot("openjev/rocketleague").run()
