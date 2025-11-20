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

MESI_Two_Level_DEBUG = True
# size_choices = ["simsmall", "simmedium", "simlarge"]

parser = argparse.ArgumentParser(
    description="A traffic generator that can be used to test a gem5 "
    "memory component."
)

parser.add_argument(
    "generator_cores", type=int, help="The number of generator cores to use."
)

if MESI_Two_Level_DEBUG:
    print("MESI_Two_Level_DEBUG is Enabled. It has 2 directory controllers")
# parser.add_argument(
#     "network_class",
#     type=str,
#     help="The network class to import and instantiate.",
#     choices=["GarnetPt2Pt", "SimplePt2Pt", "GarnetMesh"],
# )

# parser.add_argument(
#     "benchmark",
#     type=str,
#     # nargs="*",
#     help="Input the benchmark.",
# )

# parser.add_argument(
#     "size",
#     type=str,
#     help="Simulation benchmark Size",
#     choices=size_choices,
#     # nargs="*",
# )

# parser.add_argument(
#     "mem_args",
#     nargs="*",
#     help="The arguments needed to instantiate the memory class.",
# )


#Sneha_Feb1_23
# def cache_factory():
#     return MIExampleCacheNetwork(
#         size="2kB", 
#         assoc=8,
#         network=args.network_class)


#Sneha_Feb1_23

args = parser.parse_args()
# print(args.mem_args)

# cache_hierarchy = MIExampleCacheNetwork(
#     size="32kB",
#     assoc=8,
#     network=args.network_class,
# )
#Sneha_June7_23
#domain0 = SrcClockDomain(clock='0.5GHz', voltage_domain = VoltageDomain())
#Sneha_June7_23
cache_hierarchy = MESITwoLevelCacheNetwork(
    l1d_size="32kB",
    l1d_assoc=8,
    l1i_size="32kB",
    l1i_assoc=8,
    l2_size="256kB",
    l2_assoc=16,
    num_l2_banks=2,
)
#Sneha_Feb1_23
# cache_hierarchy = cache_factory()

# memory = SingleChannelDDR3_1600(*args.mem_args)
memory = DualChannelDDR4_2400(size="8GB")
# print(memory)
# print(memory.get_size())
# generator = LinearGenerator(
#             duration="250us",
#             rate="40GB/s",
#             num_cores=args.generator_cores,
#             max_addr=memory.get_size()
#         )
#Sneha_Feb1_23

#Sneha_Feb1_23
# if(args.generator_cores==64):
#     s_dir_controllers=4
# else:
#     s_dir_controllers=2

# #print(s_dir_controllers)
# memory=[]
# for i in range(s_dir_controllers):
#     print("Printing Directory Controller", i)
#     mem = SingleChannelDDR3_1600(args.mem_args[i])
#     memory.append(mem)

# generator = LinearGenerator(
#             duration="250us",
#             rate="40GB/s",
#             num_cores=args.generator_cores,
#             max_addr=sum([j.get_size() for j in memory])
#         )
#Sneha_Feb1_23

# processor = SimpleSwitchableProcessor(
#     starting_core_type=CPUTypes.KVM,
#     switch_core_type=CPUTypes.TIMING,
#     isa=ISA.X86,
#     num_cores=args.generator_cores,
# )

processor = SimpleProcessor(cpu_type=CPUTypes.TIMING, isa=ISA.X86, num_cores=args.generator_cores)
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

# motherboard = TestBoard(
#     clk_freq="3GHz",
#     #Sneha_Feb1_23z
#     #processor=generator,  # We pass the traffic generator as the processor.
#     #Sneha_Feb1_23
#     generator=generator,
#     memory=memory,
#     cache_hierarchy=cache_hierarchy,
# )
# root = Root(full_system=False, system=motherboard)
# #Sneha_Feb1_23
# motherboard._pre_instantiate()
# #Sneha_Feb1_23
# m5.instantiate()
# generator.start_traffic()
# print("Beginning simulation!")
# exit_event = m5.simulate()
# print(
#     "Exiting @ tick {} because {}.".format(m5.curTick(), exit_event.getCause())
# )

# command = (
#     "cd /home/gem5/parsec-benchmark;".format(args.benchmark)
#     + "source env.sh;"
#     + "parsecmgmt -a run -p {} -c gcc-hooks -i {} \
#         -n {};".format(
#         args.benchmark, args.size, "2"
#     )
#     + "sleep 5;"
#     + "m5 exit;"
# )


# print("Done with command")
# board.set_kernel_disk_workload(
#     # The x86 linux kernel will be automatically downloaded to the
#     # `~/.cache/gem5` directory if not already present.
#     # PARSEC benchamarks were tested with kernel version 4.19.83
#     kernel=Resource("x86-linux-kernel-4.19.83"),
#     # The x86-parsec image will be automatically downloaded to the
#     # `~/.cache/gem5` directory if not already present.
#     disk_image=Resource("x86-parsec"),
#     readfile_contents=command,
# )


# # functions to handle different exit events during the simuation
# def handle_workbegin():
#     print("Done booting Linux")
#     print("Resetting stats at the start of ROI!")
#     m5.stats.reset()
#     processor.switch()
#     yield False


# def handle_workend():
#     print("Dump stats at the end of the ROI!")
#     m5.stats.dump()
#     yield True


# simulator = Simulator(
#     board=board,
#     on_exit_event={
#         ExitEvent.WORKBEGIN: handle_workbegin(),
#         ExitEvent.WORKEND: handle_workend(),
#     },
# )

# # # We maintain the wall clock time.

# globalStart = time.time()

# print("Running the simulation")
# print("Using KVM cpu")

# m5.stats.reset()

# # We start the simulation
# simulator.run()

# print("All simulation events were successful.")

# # We print the final simulation statistics.

# print("Done with the simulation")
# print()
# print("Performance statistics:")

# print("Simulated time in ROI: " + ((str(simulator.get_roi_ticks()[0]))))
# print(
#     "Ran a total of", simulator.get_current_tick() / 1e12, "simulated seconds"
# )
# print(
#     "Total wallclock time: %.2fs, %.2f min"
#     % (time.time() - globalStart, (time.time() - globalStart) / 60)
# )

#binary=CustomResource('/media/sneha/910ba927-5981-470b-b96a-ffc1b9f29a07/sneha/Documents/GitHub/gem5_sneha/mibench/automotive/susan/susan')
# binary=CustomResource('/media/sneha/910ba927-5981-470b-b96a-ffc1b9f29a07/sneha/Documents/GitHub/gem5_sneha/mibench/automotive/qsort/qsort_large')
# binary=CustomResource('/media/sneha/910ba927-5981-470b-b96a-ffc1b9f29a07/sneha/Documents/GitHub/gem5_sneha/mibench/automotive/bitcount/bitcnts')
#binary=CustomResource('/media/sneha/910ba927-5981-470b-b96a-ffc1b9f29a07/sneha/Documents/GitHub/gem5_sneha/mibench/automotive/basicmath/basicmath_small')
# binary=CustomResource('/home/sneha/Github_Repos/gem5_Sep_23_25/tests/test-progs/hello/bin/x86/linux/hello')
#binary=CustomResource('/media/sneha/910ba927-5981-470b-b96a-ffc1b9f29a07/sneha/Documents/GitHub/gem5_sneha/mibench/telecomm/gsm/bin/toast')

# board.set_se_binary_workload(
#     # The `Resource` class reads the `resources.json` file from the gem5
#     # resources repository:
#     # https://gem5.googlesource.com/public/gem5-resource.
#     # Any resource specified in this file will be automatically retrieved.
#     # At the time of writing, this file is a WIP and does not contain all
#     # resources. Jira ticket: https://gem5.atlassian.net/browse/GEM5-1096
#     Resource("arm-hello64-static")
# )
############ Susan ##############
# board.set_se_binary_workload(binary=binary, arguments=['/media/sneha/910ba927-5981-470b-b96a-ffc1b9f29a07/sneha/Documents/GitHub/gem5_sneha/mibench/automotive/susan/input_small.pgm', '/media/sneha/910ba927-5981-470b-b96a-ffc1b9f29a07/sneha/Documents/GitHub/gem5_sneha/mibench/automotive/susan/output_small.smoothing.pgm', '-s']
#     # The `Resource` class reads the `resources.json` file from the gem5
#     # resources repository:
#     # https://gem5.googlesource.com/public/gem5-resource.
#     # Any resource specified in this file will be automatically retrieved.
#     # At the time of writing, this file is a WIP and does not contain all
#     # resources. Jira ticket: https://gem5.atlassian.net/browse/GEM5-1096
#     #Resource("arm-hello64-static")
# )

############ qsort ##############
# board.set_se_binary_workload(binary=binary, arguments=['/media/sneha/910ba927-5981-470b-b96a-ffc1b9f29a07/sneha/Documents/GitHub/gem5_sneha/mibench/automotive/qsort/input_large.dat']
#     # The `Resource` class reads the `resources.json` file from the gem5
#     # resources repository:
#     # https://gem5.googlesource.com/public/gem5-resource.
#     # Any resource specified in this file will be automatically retrieved.
#     # At the time of writing, this file is a WIP and does not contain all
#     # resources. Jira ticket: https://gem5.atlassian.net/browse/GEM5-1096
#     #Resource("arm-hello64-static")
# )

# ########### bitcount ##############
# board.set_se_binary_workload(binary=binary, arguments=['bitcnts', '75000']
#     # The `Resource` class reads the `resources.json` file from the gem5
#     # resources repository:
#     # https://gem5.googlesource.com/public/gem5-resource.
#     # Any resource specified in this file will be automatically retrieved.
#     # At the time of writing, this file is a WIP and does not contain all
#     # resources. Jira ticket: https://gem5.atlassian.net/browse/GEM5-1096
#     #Resource("arm-hello64-static")
# )

# ########### qsort ##############
# board.set_se_binary_workload(binary=binary
#     # The `Resource` class reads the `resources.json` file from the gem5
#     # resources repository:
#     # https://gem5.googlesource.com/public/gem5-resource.
#     # Any resource specified in this file will be automatically retrieved.
#     # At the time of writing, this file is a WIP and does not contain all
#     # resources. Jira ticket: https://gem5.atlassian.net/browse/GEM5-1096
#     #Resource("arm-hello64-static")
# )

# ########### basicmath ##############
# board.set_se_binary_workload(binary=binary
#     # The `Resource` class reads the `resources.json` file from the gem5
#     # resources repository:
#     # https://gem5.googlesource.com/public/gem5-resource.
#     # Any resource specified in this file will be automatically retrieved.
#     # At the time of writing, this file is a WIP and does not contain all
#     # resources. Jira ticket: https://gem5.atlassian.net/browse/GEM5-1096
#     #Resource("arm-hello64-static")
# )
binary = ' '
############ CRC ##############
board.set_se_binary_workload(binary=binary,
    # The `Resource` class reads the `resources.json` file from the gem5
    # resources repository:
    # https://gem5.googlesource.com/public/gem5-resource.
    # Any resource specified in this file will be automatically retrieved.
    # At the time of writing, this file is a WIP and does not contain all
    # resources. Jira ticket: https://gem5.atlassian.net/browse/GEM5-1096
    #Resource("arm-hello64-static")
)

# binary=CustomResource('/media/sneha/910ba927-5981-470b-b96a-ffc1b9f29a07/sneha/Documents/GitHub/gem5_sneha/tests/test-progs/hello/bin/x86/linux/hello')
# # board.set_se_binary_workload(
# #     # The `Resource` class reads the `resources.json` file from the gem5
# #     # resources repository:
# #     # https://gem5.googlesource.com/public/gem5-resource.
# #     # Any resource specified in this file will be automatically retrieved.
# #     # At the time of writing, this file is a WIP and does not contain all
# #     # resources. Jira ticket: https://gem5.atlassian.net/browse/GEM5-1096
# #     Resource("arm-hello64-static")
# # )

# board.set_se_binary_workload(binary=binary
#     # resources repository:
#     # https://gem5.googlesource.com/public/gem5-resource.
#     # Any resource specified in this file will be automatically retrieved.
#     # At the time of writing, this file is a WIP and does not contain all
#     # resources. Jira ticket: https://gem5.atlassian.net/browse/GEM5-1096
#     #Resource("arm-hello64-static")
# )

# Lastly we run the simulation.
simulator = Simulator(board=board)
simulator.run()

print(
    "Exiting @ tick {} because {}.".format(
        simulator.get_current_tick(), simulator.get_last_exit_event_cause()
    )
)
