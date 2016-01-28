#!/usr/bin/python

def configure_federation(federation, module):
    for f in federation:
        module.run_command(['su', '-', 'irods', '-c', 'iadmin mkzone {0} remote {1}:{2}'.format(f['zone_name'], f['icat_host'], f['zone_port'])], check_rc=True)
    module.run_command(['su', '-', 'irods', '-c', '/var/lib/irods/iRODS/irodsctl restart'], check_rc=True) # reServer requires restart, possibly for server_config reload

def main():
    module = AnsibleModule(
        argument_spec = dict(
            federation=dict(type='list', required=True),
        ),
        supports_check_mode=False,
    )

    configure_federation(module.params['federation'], module)
    result = {}
    result['changed'] = True
    result['complex_args'] = module.params

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
