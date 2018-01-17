# -*- coding: utf-8 -*-
from shipit_static_analysis import Issue
from cli_common.command import run
from cli_common.log import get_logger
import itertools
import json
import os

logger = get_logger(__name__)

ISSUE_MARKDOWN = '''
## mozlint - {linter}

- **Path**: {path}
- **Level**: {level}
- **Line**: {line}
- **In patch**: {in_patch}
- **Third Party**: {third_party}
- **Publishable**: {publishable}

```
{message}
```
'''


class MozLintIssue(Issue):
    def __init__(self, repo_dir, repo_path, modified_lines, column, level, lineno, linter, message, rule, **kwargs):
        self.nb_lines = 1
        self.repo_dir = repo_dir
        self.path = repo_path
        self.column = column
        self.level = level
        self.line = lineno
        self.linter = linter
        self.message = message
        self.rule = rule
        self.in_patch = self.line in modified_lines

    def __str__(self):
        return '{} issue {} {} line {}'.format(
            self.linter,
            self.level,
            self.path,
            self.line,
        )

    def is_publishable(self):
        '''
        Publishable when:
        * line is modified by dev.
        * file is not 3rd party
        '''
        return self.in_patch and not self.is_third_party()

    def as_text(self):
        '''
        Build the text content for reporters
        '''
        return '{}: {} [{}: {}]'.format(
            self.level.capitalize(),
            self.message,
            self.linter,
            self.rule,
        )

    def as_markdown(self):
        '''
        Build the Markdown content for debug email
        '''
        return ISSUE_MARKDOWN.format(
            linter=self.linter,
            path=self.path,
            level=self.level,
            line=self.line,
            message=self.message,
            third_party=self.is_third_party() and 'yes' or 'no',
            in_patch=self.in_patch and 'yes' or 'no',
            publishable=self.is_publishable() and 'yes' or 'no',
        )


class MozLint(object):
    '''
    Exposes mach lint capabilities
    '''
    def __init__(self, repo_dir):
        self.repo_dir = repo_dir

        # Check we have a Shell set in env
        # This is needed for mach + mozlint execution
        assert 'SHELL' in os.environ, \
            'Missing SHELL environment variable'

    def run(self, files):
        '''
        List all issues found by mozlint on specified files
        '''
        return list(itertools.chain.from_iterable([
            self.find_issues(path, lines) or []
            for path, lines in files.items()
        ]))

    def find_issues(self, path, modified_lines):
        '''
        Run mozlint through mach, without gecko-env
        '''

        # Run mozlint on a file
        command = [
            './mach', 'lint',
            '-f', 'json',
            '--no-ignore',
            path
        ]
        returncode, output, error = run(' '.join(command), cwd=self.repo_dir)
        if returncode == 0:
            logger.debug('No Mozlint errors', path=path)
            return

        # Load output as json
        # Only consider last line, as ./mach lint may output
        # linter setup output on stdout :/
        try:
            lines = list(filter(None, output.decode('utf-8').split('\n')))
            payload = json.loads(lines[-1])
        except json.decoder.JSONDecodeError:
            logger.warn('Invalid json output', path=path)
            return

        full_path = os.path.join(self.repo_dir, path)
        if full_path not in payload:
            logger.warn('Missing path in linter output', path=path)
            return

        return [
            MozLintIssue(self.repo_dir, path, modified_lines, **issue)
            for issue in payload[full_path]
        ]
