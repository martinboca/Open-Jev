from pathlib import Path
from time import sleep

from rlbot import flat
from rlbot.managers import MatchManager

MATCH_CONFIG_FILE = "rlbot.toml"

if __name__ == "__main__":
    match_manager = MatchManager()
    match_manager.start_match(Path(__file__).parent / MATCH_CONFIG_FILE)
    sleep(5)
    while (match_manager.packet is None
           or match_manager.packet.match_info.match_phase != flat.MatchPhase.Ended):
        sleep(0.1)
    match_manager.shut_down()
