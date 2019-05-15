import sys
import getopt
import logging
import gn_timer_py2

"""
Use this module to repair Abaqus .inp files with node placement errors in 
zero-thickness 3D elements, such as cohesive elements. This can occur 
sometimes when, due to precision errors, nodes move slightly and the node 
numbering scheme is disrupted.

To use as a standalone, change the following variables in the block at the 
end of the file:
    default_old_inp_file: the path of the inp file you wish to modify
    default_new_inp_file: the path where the new inp file will be created
    default_element_types: choose 'cohesives' or 'all' depending on whether 
        or not you only want to adjust nodes which are part of cohesive 
        elements, or nodes which are part of any type of element
    default_tolerance = .001
        maximum distance between like coordinates of two nodes for the two 
        nodes to still be considered in the "same place"
        
To use from the command line, call zero_thickness_repair.py with the following
options corresponding to the variables listed above:
    -i: old_inp_file
    -n: new_inp_file
    -e: element_types
    -t: tolerance
    
To use from another module, import and call the function coord_snap() with 
the above options as arguments.
"""

time_me = gn_timer_py2.Timer.timer


@time_me
def read_node_coordinates(inp_file_handle, logger):
    """
    Reads node coordinates and returns a dict with node numbers as keys and
    coordinates as values
    :param inp_file_handle: inp file handle object
    :param logger: logger object for debugging
    :return node_coords_dict: dict of node numbers and coordinates
    """
    node_coords_dict = dict()
    while True:
        last_pos = inp_file_handle.tell()
        line = inp_file_handle.readline()
        if line == '':
            logger.error("end of .inp file reached before end of node section")
            raise Exception('end of inp file')
        if line.startswith('*'):
            inp_file_handle.seek(last_pos)
            break
        line_stuff = line.rstrip().split(',')
        node_number = int(line_stuff[0])
        node_coords_dict[node_number] = tuple(float(x) for x in line_stuff[1:])
    logger.info("read {0} nodes".format(len(node_coords_dict)))
    return node_coords_dict


@time_me
def identify_relevant_nodes(inp_file_handle, logger):
    """
    Identifies nodes which are contained in a group of elements of like type
    :param inp_file_handle: open inp file handle object
    :param logger: logger object for debugging
    :return: relevant_node_groups, a list of lists. Each interior list is a
    list of nodes within the same element, which may need to be adjusted to
    each other.
    """
    relevant_node_groups = list()
    while True:
        last_pos = inp_file_handle.tell()
        line = inp_file_handle.readline()
        if line == '':
            logger.error("end of .inp file reached amidst an element section")
            raise Exception("end of .inp file reached")
        if line.startswith('*'):
            inp_file_handle.seek(last_pos)
            break
        line_parts = line.rstrip().split(',')
        relevant_node_groups.append([int(line_part)
                                     for line_part in line_parts[1:]])
    return relevant_node_groups


@time_me
def adjust_nodes(node_coords_dict,
                 relevant_node_groups,
                 tolerance,
                 logger):
    """
    for each relevant node in a given list, check to see if the coordinates
    of any other nodes in a given dictionary of node coordinates are very
    close; if they are, modify the dictionary by replacing the other node's
    coordinates with the first node's coordinates
    :param node_coords_dict: dict with node numbers as keys and node
        coordinates as values
    :param relevant_node_groups: list of lists of nodes to check positions for
    :param tolerance: value defining "very close"
    :param logger: logger object for debugging
    :return adjusted_coords_dict: a dict, like node_coords_dict,
        but containing only the nodes and their coords which have been adjusted
    """
    substitutions = 0
    adjusted_nodes = list()
    for node_group in relevant_node_groups:
        for i, node_1_number in enumerate(node_group):
            node_1_coords = node_coords_dict[node_1_number]
            for node_2_number in node_group[i + 1:]:
                node_2_coords = node_coords_dict[node_2_number]
                x_diff = node_1_coords[0] - node_2_coords[0]
                y_diff = node_1_coords[1] - node_2_coords[1]
                z_diff = node_1_coords[2] - node_2_coords[2]
                if all((abs(x_diff) < tolerance,
                        abs(y_diff) < tolerance,
                        abs(z_diff) < tolerance)):
                    node_coords_dict[node_2_number] = \
                        node_coords_dict[node_1_number]
                    adjusted_nodes.append(node_2_number)
                    substitutions += 1
    adjusted_nodes = list(set(adjusted_nodes))
    adjusted_coords = [node_coords_dict[node_number]
                       for node_number in adjusted_nodes]
    adjusted_coords_dict = dict(zip(adjusted_nodes, adjusted_coords))
    logger.info("made {0} substitutions".format(substitutions))
    return adjusted_coords_dict


@time_me
def write_new_inp_file(old_inp_file_handle,
                       new_inp_file_handle,
                       adjusted_node_coords,
                       logger):
    """
    copy the contents of the old inp file to the new inp file, but modify the
     node section
    :param old_inp_file_handle: file handle object for the old inp file
    :param new_inp_file_handle: file handle object for the new inp file
    :param adjusted_node_coords: dictionary containing modified node coordinates
    :param logger: logger object for debugging
    :return:
    """
    while True:
        old_line = old_inp_file_handle.readline()
        if old_line == '':
            break
        if old_line.startswith('*Node\n'):
            new_inp_file_handle.write(old_line)
            write_new_node_section(old_inp_file_handle,
                                   adjusted_node_coords,
                                   new_inp_file_handle,
                                   logger)
        else:
            new_inp_file_handle.write(old_line)
    return


@time_me
def write_new_node_section(old_inp_file_handle,
                           adjusted_node_coords,
                           new_inp_file_handle,
                           logger):
    """
    copy the node section from the old inp file to the new inp file,
    but modify the coordinates of some nodes based on the node_coords_dict
    :param old_inp_file_handle: file handle object for the old inp file
    :param adjusted_node_coords: dict of node coordinates
    :param new_inp_file_handle: file handle object for the new inp file
    :param logger: logger object for debugging
    :return:
    """
    while True:
        old_pos = old_inp_file_handle.tell()
        old_line = old_inp_file_handle.readline()
        if old_line == '':
            logger.error('end of .inp file reached while parsing node section')
            raise Exception("end of .inp file reached while parsing node "
                            "section")
        if old_line.startswith('*'):
            old_inp_file_handle.seek(old_pos)
            break
        node_number = int(old_line.split(',')[0])
        if node_number in adjusted_node_coords:
            node_coords = adjusted_node_coords[node_number]
            new_line = '{0},{1},{2},{3}\n'.format(node_number, *node_coords)
        else:
            new_line = old_line
        new_inp_file_handle.write(new_line)
    return


@time_me
def parse_old_inp_file(old_inp_file_handle, inp_el_key, logger):
    """
    read the old inp file, build a dict with node numbers as keys and
    nodal coordinates as values, and build a list of nodes which may need
    their coordinates adjusted
    :param old_inp_file_handle: file handle object for the old inp file
    :param inp_el_key: string indicating if the search for relevant nodes
        should be restricted to just cohesive elements, or expanded to all
        elements
    :param logger: logger object for debugging
    :return:
        a dict with node numbers as keys and nodal coordinates as values
        a list of lists of node numbers
    """
    node_coords_dict = dict()
    relevant_node_groups = list()
    while True:
        line = old_inp_file_handle.readline()
        if line == '':
            break
        if line.startswith(inp_el_key):
            relevant_node_groups.extend(identify_relevant_nodes(
                old_inp_file_handle, logger))
            continue
    # relevant_node_groups = list(set(relevant_node_groups))
    old_inp_file_handle.seek(0)
    while True:
        line = old_inp_file_handle.readline()
        if line == '':
            break
        if line.startswith('*Node\n'):
            node_coords_dict = read_node_coordinates(old_inp_file_handle,
                                                     logger)
            continue
    return node_coords_dict, relevant_node_groups


@time_me
def coord_snap(old_inp_file_path,
               new_inp_file_path,
               element_types,
               tolerance,
               logger=None):
    """
    essentially the main function for this module
    :param old_inp_file_path: file path to the inp file to copy and modify
    :param new_inp_file_path: file path to the new inp file to create
    :param element_types: keyword indicating whether to search for nodes
        which need modification only within cohesive elements or within all
        elements
    :param tolerance: maximum distance between each nodal coordinate for two
        nodes' positions to be considered identical
    :param logger: logger object for debugging
    :return:
    """
    # create logger in the event this module is called as a standalone
    created_new_logger = False
    if not logger:
        created_new_logger = True
        logger = logging.getLogger(__name__)
        logger_console_handler = logging.StreamHandler()
        logger_console_handler.setLevel(logging.INFO)
        lc_formatter = logging.Formatter("%(message)s")
        logger_console_handler.setFormatter(lc_formatter)
        logger.addHandler(logger_console_handler)

    try:
        if element_types == 'cohesives':
            inp_el_key = '*Element, type=COH3D'
        elif element_types == 'all':
            inp_el_key = '*Element, type='
        else:
            logger.error("element_types bad argument")
            raise ValueError("incorrect argument for element_types")
        with open(old_inp_file_path, 'r') as old_inp_file_handle:
            node_coords_dict, relevant_node_groups = \
                parse_old_inp_file(old_inp_file_handle, inp_el_key, logger)
            adjusted_node_coords = adjust_nodes(node_coords_dict,
                                                relevant_node_groups,
                                                tolerance,
                                                logger)
            with open(new_inp_file_path, 'w') as new_inp_file_handle:
                old_inp_file_handle.seek(0)
                write_new_inp_file(old_inp_file_handle,
                                   new_inp_file_handle,
                                   adjusted_node_coords,
                                   logger)

    # release loggers
    finally:
        if created_new_logger:
            for handler in logger.handlers:
                handler.close()
                logger.removeFilter(handler)
            logger.handlers = []
    return


def main(argv):
    """
    parse command line arguments and call coord_snap()
    :param argv:
    :return:
    """
    old_inp_file_path = ''
    new_inp_file_path = ''
    element_types = 'cohesives'
    tolerance = .001
    try:
        opts, args = getopt.getopt(argv, "i:n:e:t:")
    except getopt.GetoptError:
        print("inp_editor.py -i <inp_file> -n <new_inp_file> -e "
              "<element_types ('cohesives' or 'all')> -t <tolerance>")
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-i':
            old_inp_file_path = arg
        elif opt == '-n':
            new_inp_file_path = arg
        elif opt == '-e':
            element_types = arg
        elif opt == '-t':
            tolerance = float(arg)
    coord_snap(old_inp_file_path, new_inp_file_path, element_types,
               tolerance)
    return


if __name__ == '__main__':
    default_old_inp_file = 'misaligned_large_geom1B.inp'
    default_new_inp_file = 'new_test.inp'
    default_element_types = 'cohesives'
    default_tolerance = .001
    if not sys.argv[1:]:
        cl_argv = ['-i', default_old_inp_file,
                   '-n', default_new_inp_file,
                   '-e', default_element_types,
                   '-t', default_tolerance]
    else:
        cl_argv = sys.argv[1:]
    main(cl_argv)
    gn_timer_py2.print_times()
    print("success")
