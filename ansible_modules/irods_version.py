#!/usr/bin/python

import json

def main():
    module = AnsibleModule(
        argument_spec = dict(
        ),
        supports_check_mode=False,
    )

    result = {
        'changed': True,
        'complex_args': module.params,
        'irods_version': get_irods_version(),
    }
    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
