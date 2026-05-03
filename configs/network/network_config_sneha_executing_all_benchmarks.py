import argparse
import importlib

# Sneha_Feb11_23
import time

import m5
from m5.objects import Root

from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.boards.test_board import TestBoard
from gem5.components.boards.x86_board import X86Board
from gem5.components.cachehierarchies.ruby.mesi_two_level_cache_hierarchy import (
    MESITwoLevelCacheHierarchy,
)

# Sneha_Feb11_23
# from gem5.components.cachehierarchies.ruby.mi_example_cache_network import MIExampleCacheNetwork
from gem5.components.cachehierarchies.ruby.mesi_two_level_cache_network import (
    MESITwoLevelCacheNetwork,
)
from gem5.components.memory import (
    DualChannelDDR4_2400,
    SingleChannelDDR3_1600,
)
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.linear_generator import LinearGenerator
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.processors.simple_switchable_processor import (
    SimpleSwitchableProcessor,
)
from gem5.isas import ISA

# from gem5.resources.resource import Resource
from gem5.resources.resource import (
    CustomResource,
    Resource,
)
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.simulator import Simulator

# size_choices = ["simsmall", "simmedium", "simlarge"]

parser = argparse.ArgumentParser(
    description="A traffic generator that can be used to test a gem5 "
    "memory component."
)

parser.add_argument(
    "generator_cores", type=int, help="The number of generator cores to use."
)

args = parser.parse_args()

cache_hierarchy = MESITwoLevelCacheNetwork(
    l1d_size="32kB",
    l1d_assoc=8,
    l1i_size="32kB",
    l1i_assoc=8,
    l2_size="256kB",
    l2_assoc=16,
    num_l2_banks=2,
    high_criticality_src_ids=[
        0,
        2,
        3,
        4,
        6,
        7,
        9,
        10,
        11,
        13,
        14,
        16,
        17,
        18,
        20,
        21,
        23,
        24,
        25,
        27,
        28,
        30,
        31,
        32,
        34,
    ],
)

memory = DualChannelDDR4_2400(size="8GB")

processor = SimpleProcessor(
    cpu_type=CPUTypes.TIMING, isa=ISA.X86, num_cores=args.generator_cores
)

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

# binary = CustomResource(
#     "/home/sneha/Github_Repos/gem5_Sep_23_25/tests/test-progs/hello/bin/x86/linux/hello"
# )
# board.set_se_binary_workload(binary=binary)

binary1 = CustomResource(
    "/home/sneha/Github_Repos/mibench/automotive/susan/susan"
)
arguments1 = [
    "/home/sneha/Github_Repos/mibench/automotive/susan/susan/input_large.pgm",
    "/home/sneha/Github_Repos/mibench/automotive/susan/output_large.smoothing.pgm",
    "-s",
]

binary2 = CustomResource(
    "/home/sneha/Github_Repos/mibench/automotive/qsort/qsort_large"
)
arguments2 = [
    "/home/sneha/Github_Repos/mibench/automotive/qsort/input_large.dat"
]

binary3 = CustomResource(
    "/home/sneha/Github_Repos/mibench/automotive/bitcount/bitcnts"
)
arguments3 = ["bitcnts", "1125000"]

binary4 = CustomResource(
    "/home/sneha/Github_Repos/mibench/automotive/basicmath/basicmath_small"
)
arguments4 = [""]

binary5 = CustomResource("/home/sneha/Github_Repos/mibench/telecomm/CRC32/crc")
arguments5 = ["/home/sneha/Github_Repos/mibench/telecomm/adpcm/data/large.pcm"]

binary6 = CustomResource(
    "/home/sneha/Github_Repos/mibench/network/dijkstra/dijkstra_large"
)
arguments6 = ["/home/sneha/Github_Repos/mibench/network/dijkstra/input.dat"]

binary7 = CustomResource(
    "/home/sneha/Github_Repos/mibench/network/patricia/patricia"
)
arguments7 = ["/home/sneha/Github_Repos/mibench/network/patricia/large.udp"]

board.set_se_multi_binary_workload(
    binaries=[
        binary1,
        binary2,
        binary3,
        binary4,
        binary5,
        binary6,
        binary7,
        binary1,
        binary2,
        binary3,
        binary4,
        binary5,
        binary6,
        binary7,
        binary1,
        binary2,
        binary3,
        binary4,
        binary5,
        binary6,
        binary7,
        binary1,
        binary2,
        binary3,
        binary4,
        binary5,
        binary6,
        binary7,
        binary1,
        binary2,
        binary3,
        binary4,
        binary5,
        binary6,
        binary7,
        binary1,
        binary2,
        binary3,
        binary4,
        binary5,
        binary6,
        binary7,
        binary1,
        binary2,
        binary3,
        binary4,
        binary5,
        binary6,
        binary7,
        binary1,
        binary2,
        binary3,
        binary4,
        binary5,
        binary6,
        binary7,
        binary1,
        binary2,
        binary3,
        binary4,
        binary5,
        binary6,
        binary7,
        binary1,
    ],
    arguments=[
        arguments1,
        arguments2,
        arguments3,
        arguments4,
        arguments5,
        arguments6,
        arguments7,
        arguments1,
        arguments2,
        arguments3,
        arguments4,
        arguments5,
        arguments6,
        arguments7,
        arguments1,
        arguments2,
        arguments3,
        arguments4,
        arguments5,
        arguments6,
        arguments7,
        arguments1,
        arguments2,
        arguments3,
        arguments4,
        arguments5,
        arguments6,
        arguments7,
        arguments1,
        arguments2,
        arguments3,
        arguments4,
        arguments5,
        arguments6,
        arguments7,
        arguments1,
        arguments2,
        arguments3,
        arguments4,
        arguments5,
        arguments6,
        arguments7,
        arguments1,
        arguments2,
        arguments3,
        arguments4,
        arguments5,
        arguments6,
        arguments7,
        arguments1,
        arguments2,
        arguments3,
        arguments4,
        arguments5,
        arguments6,
        arguments7,
        arguments1,
        arguments2,
        arguments3,
        arguments4,
        arguments5,
        arguments6,
        arguments7,
        arguments1,
    ],
)

# Lastly we run the simulation.
simulator = Simulator(board=board)
simulator.run()

print(
    "Exiting @ tick {} because {}.".format(
        simulator.get_current_tick(), simulator.get_last_exit_event_cause()
    )
)
