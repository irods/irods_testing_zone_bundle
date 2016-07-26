#!/usr/bin/python
import json


def configure_federation(federation, disable_client_server_negotiation, module):
    for f in federation:
        module.run_command(['su', '-', 'irods', '-c', 'iadmin mkzone {0} remote {1}:{2}'.format(f['zone_name'], f['icat_host'], f['zone_port'])], check_rc=True)
    if disable_client_server_negotiation and get_irods_version() >= (4, 1):
        with open('/var/lib/irods/.irods/irods_environment.json') as f:
            d = json.load(f)
        d['irods_client_server_negotiation'] = 'off'
        with open('/var/lib/irods/.irods/irods_environment.json', 'w') as f:
            json.dump(d, f, indent=4, sort_keys=True)
    # reServer requires restart, possibly for server_config reload
    if federation:
        if get_irods_version()[0:2] < (4, 2):
            module.run_command(['su', '-', 'irods', '-c', '/var/lib/irods/iRODS/irodsctl restart'], check_rc=True)
        else:
            module.run_command(['su', '-', 'irods', '-c', '/var/lib/irods/irodsctl restart'], check_rc=True)

def main():
    module = AnsibleModule(
        argument_spec = dict(
            federation=dict(type='list', required=True),
            disable_client_server_negotiation=dict(type='bool', required=True),
        ),
        supports_check_mode=False,
    )

    configure_federation(module.params['federation'], module.params['disable_client_server_negotiation'], module)
    result = {}
    result['changed'] = True
    result['complex_args'] = module.params

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
