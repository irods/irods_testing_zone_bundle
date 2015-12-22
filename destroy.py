import argparse
import contextlib
import json
import multiprocessing
import os

import library

@contextlib.contextmanager
def deployed_zone_bundle_manager(deployed_zone_bundle, only_on_exception=False):
    try:
        yield
    except:
        destroy(deployed_zone_bundle)
        raise
    else:
        if not only_on_exception:
            destroy(deployed_zone_bundle)

def destroy(zone_bundle):
    destroy_zone_bundle(zone_bundle)

def destroy_zone_bundle(zone_bundle):
    proc_pool = library.RecursiveMultiprocessingPool(len(zone_bundle['zones']))
    proc_pool_results = [proc_pool.apply_async(destroy_zone, (zone,))
                         for zone in zone_bundle['zones']]
    [result.get() for result in proc_pool_results]

def destroy_zone(zone):
    servers = library.get_servers_from_zone(zone)
    database_config = zone['icat_server']['database_config']
    if 'deployment_information' in database_config:
        servers.append(database_config)
    proc_pool = multiprocessing.Pool(len(servers))
    proc_pool_results = [proc_pool.apply_async(library.destroy_vm,
                                             (server['deployment_information']['vm_name'],))
                       for server in servers]
    for result in proc_pool_results:
        result.get()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Destroy zone-bundle')
    parser.add_argument('--zone_bundle_input', type=str, required=True)
    args = parser.parse_args()

    with open(os.path.abspath(args.zone_bundle_input)) as f:
        zone_bundle = json.load(f)

    destroy(zone_bundle)
