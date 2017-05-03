#!/usr/bin/python

import json


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *

install_pip()
pip_install_irods_python_ci_utilities()
import irods_python_ci_utilities


def checkout_git_repo_and_run_build_hook(git_repository, git_commitish, python_script, passthrough_arguments):
    git_checkout_dir = irods_python_ci_utilities.git_clone(git_repository, git_commitish)
    return irods_python_ci_utilities.subprocess_get_output(['python', python_script] + passthrough_arguments, cwd=git_checkout_dir, check_rc=True)

def main():
    module = AnsibleModule(
        argument_spec = dict(
            git_repository=dict(type='str', required=True),
            git_commitish=dict(type='str', required=True),
            python_script=dict(type='str', required=True),
            passthrough_arguments=dict(type='list', required=True),
        ),
        supports_check_mode=False,
    )

    rc, stdout, stderr = checkout_git_repo_and_run_build_hook(module.params['git_repository'], module.params['git_commitish'], module.params['python_script'], module.params['passthrough_arguments'])

    result = {
        'changed': True,
        'complex_args': module.params,
        'irods_platform_string': get_irods_platform_string(),
        'build_hook_rc': rc,
        'build_hook_stdout': stdout,
        'build_hook_stderr': stderr,
    }
    module.exit_json(**result)

main()
