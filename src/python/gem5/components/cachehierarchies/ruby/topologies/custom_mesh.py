import math

from m5.objects import *
from m5.objects import (
    GarnetExtLink,
    GarnetIntLink,
    GarnetNetwork,
    GarnetNetworkInterface,
    GarnetRouter,
)
from m5.params import *

MESI_Two_Level_debug = True


class CustomMesh(GarnetNetwork):

    def __init__(self, ruby_system):
        super().__init__()
        self.ruby_system = ruby_system

    # Makes a generic mesh

    def connectControllers(
        self,
        l1controllers,
        l2controllers,
        dircontrollers,
        dmacontrollers,
        ncpu,
        first_dir_loc,
        second_dir_loc,
    ):
        num_routers = ncpu
        num_rows = math.isqrt(ncpu)
        if MESI_Two_Level_debug:
            print("Printing from customMesh: Number of rows=", num_rows)
        nodes = l1controllers + l2controllers + dircontrollers + dmacontrollers

        # default values for link latency and router latency.
        # Can be over-ridden on a per link/router basis
        # link_latency = 8
        link_latency = 4
        router_latency = 1

        # There must be an evenly divisible number of controllers to routers
        # Also, obviously the number or rows must be <= the number of routers
        cntrls_per_router, remainder = divmod(len(nodes), num_routers)
        assert num_rows > 0 and num_rows <= num_routers
        num_columns = int(num_routers / num_rows)
        assert num_columns * num_rows == num_routers
        # Create the routers in the mesh
        self.routers = [
            GarnetRouter(router_id=i, latency=router_latency)
            for i in range(num_routers)
        ]

        # link counter to set unique link ids
        link_count = 0

        # Add all but the remainder nodes to the list of nodes to be uniformly
        # distributed across the network.
        network_nodes = []
        remainder_nodes = []
        for node_index in range(len(nodes)):
            if node_index < (len(nodes) - remainder):
                network_nodes.append(nodes[node_index])
            else:
                remainder_nodes.append(nodes[node_index])

        # Connect each node to the appropriate router
        ext_links = []
        for i, n in enumerate(network_nodes):
            cntrl_level, router_id = divmod(i, num_routers)
            assert cntrl_level < cntrls_per_router
            ext_links.append(
                GarnetExtLink(
                    link_id=link_count,
                    ext_node=n,
                    int_node=self.routers[router_id],
                    latency=link_latency,
                )
            )
            link_count += 1

        c = first_dir_loc
        for i, n in enumerate(l2controllers):
            ext_links.append(
                GarnetExtLink(
                    link_id=link_count,
                    ext_node=n,
                    int_node=self.routers[c],
                    latency=link_latency,
                )
            )
            c = second_dir_loc
            link_count += 1

        c = first_dir_loc
        for i, n in enumerate(dircontrollers):
            ext_links.append(
                GarnetExtLink(
                    link_id=link_count,
                    ext_node=n,
                    int_node=self.routers[c],
                    latency=link_latency,
                )
            )
            c = second_dir_loc
            link_count += 1

        # Connect the remaining nodes to router 0.  These should only be
        # DMA nodes.
        for i, node in enumerate(dmacontrollers):
            assert i < remainder
            ext_links.append(
                GarnetExtLink(
                    link_id=link_count,
                    ext_node=node,
                    int_node=self.routers[0],
                    latency=link_latency,
                )
            )
            link_count += 1

        self.ext_links = ext_links

        self.netifs = [
            GarnetNetworkInterface(id=i)
            for (i, n) in enumerate(self.ext_links)
        ]

        # Create the mesh links.
        int_links = []

        # East output to West input links (weight = 1)
        for row in range(num_rows):
            for col in range(num_columns):
                if col + 1 < num_columns:
                    east_out = col + (row * num_columns)
                    west_in = (col + 1) + (row * num_columns)
                    int_links.append(
                        GarnetIntLink(
                            link_id=link_count,
                            src_node=self.routers[east_out],
                            dst_node=self.routers[west_in],
                            src_outport="East",
                            dst_inport="West",
                            latency=link_latency,
                            weight=1,
                        )
                    )
                    link_count += 1

        # West output to East input links (weight = 1)
        for row in range(num_rows):
            for col in range(num_columns):
                if col + 1 < num_columns:
                    east_in = col + (row * num_columns)
                    west_out = (col + 1) + (row * num_columns)
                    int_links.append(
                        GarnetIntLink(
                            link_id=link_count,
                            src_node=self.routers[west_out],
                            dst_node=self.routers[east_in],
                            src_outport="West",
                            dst_inport="East",
                            latency=link_latency,
                            weight=1,
                        )
                    )
                    link_count += 1

        # North output to South input links (weight = 2)
        for col in range(num_columns):
            for row in range(num_rows):
                if row + 1 < num_rows:
                    north_out = col + (row * num_columns)
                    south_in = col + ((row + 1) * num_columns)
                    int_links.append(
                        GarnetIntLink(
                            link_id=link_count,
                            src_node=self.routers[north_out],
                            dst_node=self.routers[south_in],
                            src_outport="North",
                            dst_inport="South",
                            latency=link_latency,
                            weight=1,
                        )
                    )
                    link_count += 1

        # South output to North input links (weight = 2)
        for col in range(num_columns):
            for row in range(num_rows):
                if row + 1 < num_rows:
                    north_in = col + (row * num_columns)
                    south_out = col + ((row + 1) * num_columns)
                    int_links.append(
                        GarnetIntLink(
                            link_id=link_count,
                            src_node=self.routers[south_out],
                            dst_node=self.routers[north_in],
                            src_outport="South",
                            dst_inport="North",
                            latency=link_latency,
                            weight=1,
                        )
                    )
                    link_count += 1

        # 2‑hop East -> West links (every possible 2‑hop)
        for row in range(num_rows):
            for col in range(num_columns):
                if col + 2 < num_columns:
                    src = col + (row * num_columns)
                    dst = (col + 2) + (row * num_columns)
                    int_links.append(
                        GarnetIntLink(
                            link_id=link_count,
                            src_node=self.routers[src],
                            dst_node=self.routers[dst],
                            src_outport="TwoHopEast",
                            dst_inport="TwoHopWest",
                            latency=link_latency,
                            weight=100,
                        )
                    )
                    link_count += 1

        # reverse direction for those 2‑hop links (West -> East)
        for row in range(num_rows):
            for col in range(num_columns):
                if col + 2 < num_columns:
                    src = (col + 2) + (row * num_columns)
                    dst = col + (row * num_columns)
                    int_links.append(
                        GarnetIntLink(
                            link_id=link_count,
                            src_node=self.routers[src],
                            dst_node=self.routers[dst],
                            src_outport="TwoHopWest",
                            dst_inport="TwoHopEast",
                            latency=link_latency,
                            weight=100,
                        )
                    )
                    link_count += 1

        # 2‑hop North -> South links (every possible 2‑hop)
        for col in range(num_columns):
            for row in range(num_rows):
                if row + 2 < num_rows:
                    src = col + (row * num_columns)
                    dst = col + ((row + 2) * num_columns)
                    int_links.append(
                        GarnetIntLink(
                            link_id=link_count,
                            src_node=self.routers[src],
                            dst_node=self.routers[dst],
                            src_outport="TwoHopNorth",
                            dst_inport="TwoHopSouth",
                            latency=link_latency,
                            weight=100,
                        )
                    )
                    link_count += 1

        # reverse direction for those 2‑hop links (South -> North)
        for col in range(num_columns):
            for row in range(num_rows):
                if row + 2 < num_rows:
                    src = col + ((row + 2) * num_columns)
                    dst = col + (row * num_columns)
                    int_links.append(
                        GarnetIntLink(
                            link_id=link_count,
                            src_node=self.routers[src],
                            dst_node=self.routers[dst],
                            src_outport="TwoHopSouth",
                            dst_inport="TwoHopNorth",
                            latency=link_latency,
                            weight=100,
                        )
                    )
                    link_count += 1

        # Single-hop diagonal links (NorthEast <-> SouthWest)
        # NorthEast -> SouthWest (col, row) to (col+1, row+1)
        for col in range(num_columns):
            for row in range(num_rows):
                if (col + 1 < num_columns) and (row + 1 < num_rows):
                    src = col + (row * num_columns)
                    dst = (col + 1) + ((row + 1) * num_columns)
                    int_links.append(
                        GarnetIntLink(
                            link_id=link_count,
                            src_node=self.routers[src],
                            dst_node=self.routers[dst],
                            src_outport="NorthEast",
                            dst_inport="SouthWest",
                            latency=link_latency,
                            weight=100,
                        )
                    )
                    link_count += 1

        # reverse direction (SouthWest -> NorthEast)
        for col in range(num_columns):
            for row in range(num_rows):
                if (col + 1 < num_columns) and (row + 1 < num_rows):
                    src = (col + 1) + ((row + 1) * num_columns)
                    dst = col + (row * num_columns)
                    int_links.append(
                        GarnetIntLink(
                            link_id=link_count,
                            src_node=self.routers[src],
                            dst_node=self.routers[dst],
                            src_outport="SouthWest",
                            dst_inport="NorthEast",
                            latency=link_latency,
                            weight=100,
                        )
                    )
                    link_count += 1

        # Single-hop diagonal links (NorthWest <-> SouthEast)
        # NorthWest -> SouthEast (col, row) to (col-1, row+1)
        for col in range(num_columns):
            for row in range(num_rows):
                if (col - 1 >= 0) and (row + 1 < num_rows):
                    src = col + (row * num_columns)
                    dst = (col - 1) + ((row + 1) * num_columns)
                    int_links.append(
                        GarnetIntLink(
                            link_id=link_count,
                            src_node=self.routers[src],
                            dst_node=self.routers[dst],
                            src_outport="NorthWest",
                            dst_inport="SouthEast",
                            latency=link_latency,
                            weight=100,
                        )
                    )
                    link_count += 1

        # reverse direction (SouthEast -> NorthWest)
        for col in range(num_columns):
            for row in range(num_rows):
                if (col - 1 >= 0) and (row + 1 < num_rows):
                    src = (col - 1) + ((row + 1) * num_columns)
                    dst = col + (row * num_columns)
                    int_links.append(
                        GarnetIntLink(
                            link_id=link_count,
                            src_node=self.routers[src],
                            dst_node=self.routers[dst],
                            src_outport="SouthEast",
                            dst_inport="NorthWest",
                            latency=link_latency,
                            weight=100,
                        )
                    )
                    link_count += 1

        self.int_links = int_links
