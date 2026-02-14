import m5
import argparse
import importlib
from m5.objects import Root
from gem5.components.boards.test_board import TestBoard
#Sneha_Feb11_23
import time
from gem5.components.boards.x86_board import X86Board
from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.processors.simple_switchable_processor import (
    SimpleSwitchableProcessor,
)
from gem5.components.processors.cpu_types import CPUTypes
from gem5.isas import ISA
from gem5.components.memory import DualChannelDDR4_2400
# from gem5.resources.resource import Resource
from gem5.resources.resource import Resource, CustomResource
from gem5.components.processors.simple_processor import SimpleProcessor

from gem5.simulate.simulator import Simulator
from gem5.simulate.exit_event import ExitEvent
#Sneha_Feb11_23
#from gem5.components.cachehierarchies.ruby.mi_example_cache_network import MIExampleCacheNetwork
from gem5.components.cachehierarchies.ruby.mesi_two_level_cache_network import MESITwoLevelCacheNetwork
from gem5.components.cachehierarchies.ruby.mesi_two_level_cache_hierarchy import MESITwoLevelCacheHierarchy
from gem5.components.processors.linear_generator import LinearGenerator
from gem5.components.memory import SingleChannelDDR3_1600


# size_choices = ["simsmall", "simmedium", "simlarge"]

parser = argparse.ArgumentParser(
    description="A traffic generator that can be used to test a gem5 "
    "memory component."
)

parser.add_argument(
    "generator_cores", type=int, help="The number of generator cores to use."
)

parser.add_argument(
    "network_class",
    type=str,
    help="The network class to import and instantiate.",
    choices=["GarnetPt2Pt", "SimplePt2Pt", "GarnetMesh"],
)

args = parser.parse_args()

cache_hierarchy = MESITwoLevelCacheNetwork(
    l1d_size="32kB",
    l1d_assoc=8,
    l1i_size="32kB",
    l1i_assoc=8,
    l2_size="256kB",
    l2_assoc=16,
    num_l2_banks=2
)

memory = DualChannelDDR4_2400(size="8GB")

processor = SimpleProcessor(cpu_type=CPUTypes.TIMING, isa=ISA.X86, num_cores=args.generator_cores)

print("Processor is defined")
# board = X86Board(
#     clk_freq="3GHz",
#     processor=processor,  # We pass the traffic generator as the processor.
#     memory=memory,
#     cache_hierarchy=cache_hierarchy,
# )

board = SimpleBoard(
    clk_freq="1GHz",
    processor=processor,  # We pass the traffic generator as the processor.
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

binary=CustomResource('/home/sneha/Github_Repos/gem5_Sep_23_25/tests/test-progs/hello/bin/x86/linux/hello')
board.set_se_binary_workload(binary=binary)

# Lastly we run the simulation.
simulator = Simulator(board=board)
simulator.run()

print(
    "Exiting @ tick {} because {}.".format(
        simulator.get_current_tick(), simulator.get_last_exit_event_cause()
    )
)
