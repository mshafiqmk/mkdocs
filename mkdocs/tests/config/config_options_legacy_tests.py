import contextlib
import copy
import io
import os
import re
import sys
import textwrap
import unittest
from typing import Any, Dict
from unittest.mock import patch

import mkdocs
from mkdocs.config import base
from mkdocs.config import config_options as c
from mkdocs.tests.base import tempdir
from mkdocs.utils import write_file, yaml_load


class UnexpectedError(Exception):
    pass


class TestCase(unittest.TestCase):
    @contextlib.contextmanager
    def expect_error(self, **kwargs):
        [(key, msg)] = kwargs.items()
        with self.assertRaises(UnexpectedError) as cm:
            yield
        if isinstance(msg, re.Pattern):
            self.assertRegex(str(cm.exception), f'^{key}="{msg.pattern}"$')
        else:
            self.assertEqual(f'{key}="{msg}"', str(cm.exception))

    def get_config(
        self,
        schema: type,
        cfg: Dict[str, Any],
        warnings: Dict[str, str] = {},
        config_file_path=None,
    ):
        config = base.LegacyConfig(base.get_schema(schema), config_file_path=config_file_path)
        config.load_dict(cfg)
        actual_errors, actual_warnings = config.validate()
        if actual_errors:
            raise UnexpectedError(', '.join(f'{key}="{msg}"' for key, msg in actual_errors))
        self.assertEqual(warnings, dict(actual_warnings))
        return config


class OptionallyRequiredTest(TestCase):
    def test_empty(self):
        class Schema:
            option = c.OptionallyRequired()

        conf = self.get_config(Schema, {'option': None})
        self.assertEqual(conf['option'], None)

        self.assertEqual(Schema.option.required, False)

    def test_required(self):
        class Schema:
            option = c.OptionallyRequired(required=True)

        with self.expect_error(option="Required configuration not provided."):
            self.get_config(Schema, {'option': None})

        self.assertEqual(Schema.option.required, True)

    def test_required_no_default(self):
        class Schema:
            option = c.OptionallyRequired(required=True)

        conf = self.get_config(Schema, {'option': 2})
        self.assertEqual(conf['option'], 2)

    def test_default(self):
        class Schema:
            option = c.OptionallyRequired(default=1)

        conf = self.get_config(Schema, {'option': None})
        self.assertEqual(conf['option'], 1)

    def test_replace_default(self):
        class Schema:
            option = c.OptionallyRequired(default=1)

        conf = self.get_config(Schema, {'option': 2})
        self.assertEqual(conf['option'], 2)


class TypeTest(TestCase):
    def test_single_type(self):
        class Schema:
            option = c.Type(str)

        conf = self.get_config(Schema, {'option': "Testing"})
        self.assertEqual(conf['option'], "Testing")

    def test_multiple_types(self):
        class Schema:
            option = c.Type((list, tuple))

        conf = self.get_config(Schema, {'option': [1, 2, 3]})
        self.assertEqual(conf['option'], [1, 2, 3])

        conf = self.get_config(Schema, {'option': (1, 2, 3)})
        self.assertEqual(conf['option'], (1, 2, 3))

        with self.expect_error(
            option="Expected type: (<class 'list'>, <class 'tuple'>) but received: <class 'dict'>"
        ):
            self.get_config(Schema, {'option': {'a': 1}})

    def test_length(self):
        class Schema:
            option = c.Type(str, length=7)

        conf = self.get_config(Schema, {'option': "Testing"})
        self.assertEqual(conf['option'], "Testing")

        with self.expect_error(
            option="Expected type: <class 'str'> with length 7 but received: 'Testing Long' with length 12"
        ):
            self.get_config(Schema, {'option': "Testing Long"})


class ChoiceTest(TestCase):
    def test_required(self):
        class Schema:
            option = c.Choice(('python', 'node'), required=True)

        conf = self.get_config(Schema, {'option': 'python'})
        self.assertEqual(conf['option'], 'python')

    def test_optional(self):
        class Schema:
            option = c.Choice(('python', 'node'))

        conf = self.get_config(Schema, {'option': 'python'})
        self.assertEqual(conf['option'], 'python')

        conf = self.get_config(Schema, {})
        self.assertEqual(conf['option'], None)

        conf = self.get_config(Schema, {'option': None})
        self.assertEqual(conf['option'], None)

    def test_default(self):
        class Schema:
            option = c.Choice(('a', 'b', 'c'), default='b')

        conf = self.get_config(Schema, {})
        self.assertEqual(conf['option'], 'b')

        conf = self.get_config(Schema, {'option': None})
        self.assertEqual(conf['option'], 'b')

        with self.expect_error(option="Expected one of: ('a', 'b', 'c') but received: 'go'"):
            self.get_config(Schema, {'option': 'go'})

    def test_invalid_default(self):
        with self.assertRaises(ValueError):
            c.Choice(('a', 'b'), default='c')
        with self.assertRaises(ValueError):
            c.Choice(('a', 'b'), default='c', required=True)

    def test_invalid_choice(self):
        class Schema:
            option = c.Choice(('python', 'node'))

        with self.expect_error(option="Expected one of: ('python', 'node') but received: 'go'"):
            self.get_config(Schema, {'option': 'go'})

    def test_invalid_choices(self):
        with self.assertRaises(ValueError):
            c.Choice('')
        with self.assertRaises(ValueError):
            c.Choice([])
        with self.assertRaises(ValueError):
            c.Choice(5)


class DeprecatedTest(TestCase):
    def test_deprecated_option_simple(self):
        class Schema:
            d = c.Deprecated()

        self.get_config(
            Schema,
            {'d': 'value'},
            warnings=dict(
                d="The configuration option 'd' has been deprecated and will be removed in a "
                "future release."
            ),
        )

    def test_deprecated_option_message(self):
        class Schema:
            d = c.Deprecated(message='custom message for {} key')

        self.get_config(Schema, {'d': 'value'}, warnings={'d': 'custom message for d key'})

    def test_deprecated_option_with_type(self):
        class Schema:
            d = c.Deprecated(option_type=c.Type(str))

        self.get_config(
            Schema,
            {'d': 'value'},
            warnings=dict(
                d="The configuration option 'd' has been deprecated and will be removed in a "
                "future release."
            ),
        )

    def test_deprecated_option_with_invalid_type(self):
        class Schema:
            d = c.Deprecated(option_type=c.Type(list))

        with self.expect_error(d="Expected type: <class 'list'> but received: <class 'str'>"):
            self.get_config(
                Schema,
                {'d': 'value'},
                warnings=dict(
                    d="The configuration option 'd' has been deprecated and will be removed in a "
                    "future release."
                ),
            )

    def test_removed_option(self):
        class Schema:
            d = c.Deprecated(removed=True, moved_to='foo')

        with self.expect_error(
            d="The configuration option 'd' was removed from MkDocs. Use 'foo' instead.",
        ):
            self.get_config(Schema, {'d': 'value'})

    def test_deprecated_option_with_type_undefined(self):
        class Schema:
            option = c.Deprecated(option_type=c.Type(str))

        self.get_config(Schema, {'option': None})

    def test_deprecated_option_move(self):
        class Schema:
            new = c.Type(str)
            old = c.Deprecated(moved_to='new')

        conf = self.get_config(
            Schema,
            {'old': 'value'},
            warnings=dict(
                old="The configuration option 'old' has been deprecated and will be removed in a "
                "future release. Use 'new' instead."
            ),
        )
        self.assertEqual(conf, {'new': 'value', 'old': None})

    def test_deprecated_option_move_complex(self):
        class Schema:
            foo = c.Type(dict)
            old = c.Deprecated(moved_to='foo.bar')

        conf = self.get_config(
            Schema,
            {'old': 'value'},
            warnings=dict(
                old="The configuration option 'old' has been deprecated and will be removed in a "
                "future release. Use 'foo.bar' instead."
            ),
        )
        self.assertEqual(conf, {'foo': {'bar': 'value'}, 'old': None})

    def test_deprecated_option_move_existing(self):
        class Schema:
            foo = c.Type(dict)
            old = c.Deprecated(moved_to='foo.bar')

        conf = self.get_config(
            Schema,
            {'old': 'value', 'foo': {'existing': 'existing'}},
            warnings=dict(
                old="The configuration option 'old' has been deprecated and will be removed in a "
                "future release. Use 'foo.bar' instead."
            ),
        )
        self.assertEqual(conf, {'foo': {'existing': 'existing', 'bar': 'value'}, 'old': None})

    def test_deprecated_option_move_invalid(self):
        class Schema:
            foo = c.Type(dict)
            old = c.Deprecated(moved_to='foo.bar')

        with self.expect_error(foo="Expected type: <class 'dict'> but received: <class 'str'>"):
            self.get_config(
                Schema,
                {'old': 'value', 'foo': 'wrong type'},
                warnings=dict(
                    old="The configuration option 'old' has been deprecated and will be removed in a "
                    "future release. Use 'foo.bar' instead."
                ),
            )


class IpAddressTest(TestCase):
    class Schema:
        option = c.IpAddress()

    def test_valid_address(self):
        addr = '127.0.0.1:8000'

        conf = self.get_config(self.Schema, {'option': addr})
        self.assertEqual(str(conf['option']), addr)
        self.assertEqual(conf['option'].host, '127.0.0.1')
        self.assertEqual(conf['option'].port, 8000)

    def test_valid_IPv6_address(self):
        addr = '::1:8000'

        conf = self.get_config(self.Schema, {'option': addr})
        self.assertEqual(str(conf['option']), addr)
        self.assertEqual(conf['option'].host, '::1')
        self.assertEqual(conf['option'].port, 8000)

    def test_valid_full_IPv6_address(self):
        addr = '[2001:db8:85a3::8a2e:370:7334]:123'

        conf = self.get_config(self.Schema, {'option': addr})
        self.assertEqual(conf['option'].host, '2001:db8:85a3::8a2e:370:7334')
        self.assertEqual(conf['option'].port, 123)

    def test_named_address(self):
        addr = 'localhost:8000'

        conf = self.get_config(self.Schema, {'option': addr})
        self.assertEqual(str(conf['option']), addr)
        self.assertEqual(conf['option'].host, 'localhost')
        self.assertEqual(conf['option'].port, 8000)

    def test_default_address(self):
        addr = '127.0.0.1:8000'

        class Schema:
            option = c.IpAddress(default=addr)

        conf = self.get_config(Schema, {'option': None})
        self.assertEqual(str(conf['option']), addr)
        self.assertEqual(conf['option'].host, '127.0.0.1')
        self.assertEqual(conf['option'].port, 8000)

    @unittest.skipIf(
        sys.version_info < (3, 9, 5),
        "Leading zeros allowed in IP addresses before Python3.9.5",
    )
    def test_invalid_leading_zeros(self):
        with self.expect_error(
            option="'127.000.000.001' does not appear to be an IPv4 or IPv6 address"
        ):
            self.get_config(self.Schema, {'option': '127.000.000.001:8000'})

    def test_invalid_address_range(self):
        with self.expect_error(option="'277.0.0.1' does not appear to be an IPv4 or IPv6 address"):
            self.get_config(self.Schema, {'option': '277.0.0.1:8000'})

    def test_invalid_address_format(self):
        with self.expect_error(option="Must be a string of format 'IP:PORT'"):
            self.get_config(self.Schema, {'option': '127.0.0.18000'})

    def test_invalid_address_type(self):
        with self.expect_error(option="Must be a string of format 'IP:PORT'"):
            self.get_config(self.Schema, {'option': 123})

    def test_invalid_address_port(self):
        with self.expect_error(option="'foo' is not a valid port"):
            self.get_config(self.Schema, {'option': '127.0.0.1:foo'})

    def test_invalid_address_missing_port(self):
        with self.expect_error(option="Must be a string of format 'IP:PORT'"):
            self.get_config(self.Schema, {'option': '127.0.0.1'})

    def test_unsupported_address(self):
        class Schema:
            dev_addr = c.IpAddress()

        self.get_config(
            Schema,
            {'dev_addr': '0.0.0.0:8000'},
            warnings=dict(
                dev_addr="The use of the IP address '0.0.0.0' suggests a production "
                "environment or the use of a proxy to connect to the MkDocs "
                "server. However, the MkDocs' server is intended for local "
                "development purposes only. Please use a third party "
                "production-ready server instead."
            ),
        )

    def test_unsupported_IPv6_address(self):
        class Schema:
            dev_addr = c.IpAddress()

        self.get_config(
            Schema,
            {'dev_addr': ':::8000'},
            warnings=dict(
                dev_addr="The use of the IP address '::' suggests a production environment "
                "or the use of a proxy to connect to the MkDocs server. However, "
                "the MkDocs' server is intended for local development purposes "
                "only. Please use a third party production-ready server instead."
            ),
        )


class URLTest(TestCase):
    def test_valid_url(self):
        class Schema:
            option = c.URL()

        conf = self.get_config(Schema, {'option': "https://mkdocs.org"})
        self.assertEqual(conf['option'], "https://mkdocs.org")

        conf = self.get_config(Schema, {'option': ""})
        self.assertEqual(conf['option'], "")

    def test_valid_url_is_dir(self):
        class Schema:
            option = c.URL(is_dir=True)

        conf = self.get_config(Schema, {'option': "http://mkdocs.org/"})
        self.assertEqual(conf['option'], "http://mkdocs.org/")

        conf = self.get_config(Schema, {'option': "https://mkdocs.org"})
        self.assertEqual(conf['option'], "https://mkdocs.org/")

    def test_optional(self):
        class Schema:
            option = c.URL(is_dir=True)

        conf = self.get_config(Schema, {'option': ''})
        self.assertEqual(conf['option'], '')

        conf = self.get_config(Schema, {'option': None})
        self.assertEqual(conf['option'], None)

    def test_invalid_url(self):
        class Schema:
            option = c.URL(required=True)

        with self.expect_error(option="Required configuration not provided."):
            self.get_config(Schema, {'option': None})

        for url in "www.mkdocs.org", "//mkdocs.org/test", "http:/mkdocs.org/", "/hello/":
            with self.subTest(url=url):
                with self.expect_error(
                    option="The URL isn't valid, it should include the http:// (scheme)"
                ):
                    self.get_config(Schema, {'option': url})

    def test_invalid_type(self):
        class Schema:
            option = c.URL()

        with self.expect_error(option="Expected a string, got <class 'int'>"):
            self.get_config(Schema, {'option': 1})


class EditURITest(TestCase):
    class Schema:
        repo_url = c.URL()
        repo_name = c.RepoName('repo_url')
        edit_uri_template = c.EditURITemplate('edit_uri')
        edit_uri = c.EditURI('repo_url')

    def test_repo_name_github(self):
        conf = self.get_config(
            self.Schema,
            {'repo_url': "https://github.com/mkdocs/mkdocs"},
        )
        self.assertEqual(conf['repo_name'], "GitHub")

    def test_repo_name_bitbucket(self):
        conf = self.get_config(
            self.Schema,
            {'repo_url': "https://bitbucket.org/gutworth/six/"},
        )
        self.assertEqual(conf['repo_name'], "Bitbucket")

    def test_repo_name_gitlab(self):
        conf = self.get_config(
            self.Schema,
            {'repo_url': "https://gitlab.com/gitlab-org/gitlab-ce/"},
        )
        self.assertEqual(conf['repo_name'], "GitLab")

    def test_repo_name_custom(self):
        conf = self.get_config(
            self.Schema,
            {'repo_url': "https://launchpad.net/python-tuskarclient"},
        )
        self.assertEqual(conf['repo_name'], "Launchpad")

    def test_edit_uri_github(self):
        conf = self.get_config(
            self.Schema,
            {'repo_url': "https://github.com/mkdocs/mkdocs"},
        )
        self.assertEqual(conf['edit_uri'], 'edit/master/docs/')
        self.assertEqual(conf['repo_url'], "https://github.com/mkdocs/mkdocs")

    def test_edit_uri_bitbucket(self):
        conf = self.get_config(
            self.Schema,
            {'repo_url': "https://bitbucket.org/gutworth/six/"},
        )
        self.assertEqual(conf['edit_uri'], 'src/default/docs/')
        self.assertEqual(conf['repo_url'], "https://bitbucket.org/gutworth/six/")

    def test_edit_uri_gitlab(self):
        conf = self.get_config(
            self.Schema,
            {'repo_url': "https://gitlab.com/gitlab-org/gitlab-ce/"},
        )
        self.assertEqual(conf['edit_uri'], 'edit/master/docs/')

    def test_edit_uri_custom(self):
        conf = self.get_config(
            self.Schema,
            {'repo_url': "https://launchpad.net/python-tuskarclient"},
        )
        self.assertEqual(conf['edit_uri'], None)
        self.assertEqual(conf['repo_url'], "https://launchpad.net/python-tuskarclient")

    def test_repo_name_custom_and_empty_edit_uri(self):
        conf = self.get_config(
            self.Schema,
            {'repo_url': "https://github.com/mkdocs/mkdocs", 'repo_name': 'mkdocs'},
        )
        self.assertEqual(conf['edit_uri'], 'edit/master/docs/')

    def test_edit_uri_template_ok(self):
        conf = self.get_config(
            self.Schema,
            {
                'repo_url': "https://github.com/mkdocs/mkdocs",
                'edit_uri_template': 'edit/foo/docs/{path}',
            },
        )
        self.assertEqual(conf['edit_uri_template'], 'edit/foo/docs/{path}')

    def test_edit_uri_template_errors(self):
        with self.expect_error(
            edit_uri_template=re.compile(r'.*[{}].*')  # Complains about unclosed '{' or missing '}'
        ):
            self.get_config(
                self.Schema,
                {
                    'repo_url': "https://github.com/mkdocs/mkdocs",
                    'edit_uri_template': 'edit/master/{path',
                },
            )

        with self.expect_error(edit_uri_template=re.compile(r'.*\bz\b.*')):
            self.get_config(
                self.Schema,
                {
                    'repo_url': "https://github.com/mkdocs/mkdocs",
                    'edit_uri_template': 'edit/master/{path!z}',
                },
            )

        with self.expect_error(edit_uri_template="Unknown template substitute: 'foo'"):
            self.get_config(
                self.Schema,
                {
                    'repo_url': "https://github.com/mkdocs/mkdocs",
                    'edit_uri_template': 'edit/master/{foo}',
                },
            )

    def test_edit_uri_template_warning(self):
        conf = self.get_config(
            self.Schema,
            {
                'repo_url': "https://github.com/mkdocs/mkdocs",
                'edit_uri': 'edit',
                'edit_uri_template': 'edit/master/{path}',
            },
            warnings=dict(
                edit_uri_template="The option 'edit_uri' has no effect when 'edit_uri_template' is set."
            ),
        )
        self.assertEqual(conf['edit_uri_template'], 'edit/master/{path}')


class ListOfItemsTest(TestCase):
    def test_int_type(self):
        class Schema:
            option = c.ListOfItems(c.Type(int))

        conf = self.get_config(Schema, {'option': [1, 2, 3]})
        self.assertEqual(conf['option'], [1, 2, 3])

        with self.expect_error(
            option="Expected type: <class 'int'> but received: <class 'NoneType'>"
        ):
            conf = self.get_config(Schema, {'option': [1, None, 3]})

    def test_combined_float_type(self):
        class Schema:
            option = c.ListOfItems(c.Type((int, float)))

        conf = self.get_config(Schema, {'option': [1.4, 2, 3]})
        self.assertEqual(conf['option'], [1.4, 2, 3])

        with self.expect_error(
            option="Expected type: (<class 'int'>, <class 'float'>) but received: <class 'str'>"
        ):
            self.get_config(Schema, {'option': ['a']})

    def test_list_default(self):
        class Schema:
            option = c.ListOfItems(c.Type(int), default=[])

        conf = self.get_config(Schema, {})
        self.assertEqual(conf['option'], [])

        conf = self.get_config(Schema, {'option': None})
        self.assertEqual(conf['option'], [])

    def test_none_without_default(self):
        class Schema:
            option = c.ListOfItems(c.Type(str))

        with self.expect_error(option="Required configuration not provided."):
            conf = self.get_config(Schema, {})

        with self.expect_error(option="Required configuration not provided."):
            conf = self.get_config(Schema, {'option': None})

        conf = self.get_config(Schema, {'option': ['foo']})
        self.assertEqual(conf['option'], ['foo'])

    def test_string_not_a_list_of_strings(self):
        class Schema:
            option = c.ListOfItems(c.Type(str))

        with self.expect_error(option="Expected a list of items, but a <class 'str'> was given."):
            self.get_config(Schema, {'option': 'foo'})

    def test_post_validation_error(self):
        class Schema:
            option = c.ListOfItems(c.IpAddress())

        with self.expect_error(option="'asdf' is not a valid port"):
            self.get_config(Schema, {'option': ["localhost:8000", "1.2.3.4:asdf"]})


class FilesystemObjectTest(TestCase):
    def test_valid_dir(self):
        for cls in c.Dir, c.FilesystemObject:
            with self.subTest(cls):
                d = os.path.dirname(__file__)

                class Schema:
                    option = cls(exists=True)

                conf = self.get_config(Schema, {'option': d})
                self.assertEqual(conf['option'], d)

    def test_valid_file(self):
        for cls in c.File, c.FilesystemObject:
            with self.subTest(cls):
                f = __file__

                class Schema:
                    option = cls(exists=True)

                conf = self.get_config(Schema, {'option': f})
                self.assertEqual(conf['option'], f)

    def test_missing_without_exists(self):
        for cls in c.Dir, c.File, c.FilesystemObject:
            with self.subTest(cls):
                d = os.path.join("not", "a", "real", "path", "I", "hope")

                class Schema:
                    option = cls()

                conf = self.get_config(Schema, {'option': d})
                self.assertEqual(conf['option'], os.path.abspath(d))

    def test_missing_but_required(self):
        for cls in c.Dir, c.File, c.FilesystemObject:
            with self.subTest(cls):
                d = os.path.join("not", "a", "real", "path", "I", "hope")

                class Schema:
                    option = cls(exists=True)

                with self.expect_error(option=re.compile(r"The path '.+' isn't an existing .+")):
                    self.get_config(Schema, {'option': d})

    def test_not_a_dir(self):
        d = __file__

        class Schema:
            option = c.Dir(exists=True)

        with self.expect_error(option=re.compile(r"The path '.+' isn't an existing directory.")):
            self.get_config(Schema, {'option': d})

    def test_not_a_file(self):
        d = os.path.dirname(__file__)

        class Schema:
            option = c.File(exists=True)

        with self.expect_error(option=re.compile(r"The path '.+' isn't an existing file.")):
            self.get_config(Schema, {'option': d})

    def test_incorrect_type_error(self):
        for cls in c.Dir, c.File, c.FilesystemObject:
            with self.subTest(cls):

                class Schema:
                    option = cls()

                with self.expect_error(
                    option="Expected type: <class 'str'> but received: <class 'int'>"
                ):
                    self.get_config(Schema, {'option': 1})
                with self.expect_error(
                    option="Expected type: <class 'str'> but received: <class 'list'>"
                ):
                    self.get_config(Schema, {'option': []})

    def test_with_unicode(self):
        for cls in c.Dir, c.File, c.FilesystemObject:
            with self.subTest(cls):

                class Schema:
                    dir = cls()

                conf = self.get_config(Schema, {'dir': 'юникод'})
                self.assertIsInstance(conf['dir'], str)

    def test_dir_bytes(self):
        class Schema:
            dir = c.Dir()

        with self.expect_error(dir="Expected type: <class 'str'> but received: <class 'bytes'>"):
            self.get_config(Schema, {'dir': b'foo'})

    def test_config_dir_prepended(self):
        for cls in c.Dir, c.File, c.FilesystemObject:
            with self.subTest(cls):
                base_path = os.path.dirname(os.path.abspath(__file__))

                class Schema:
                    dir = cls()

                conf = self.get_config(
                    Schema,
                    {'dir': 'foo'},
                    config_file_path=os.path.join(base_path, 'mkdocs.yml'),
                )
                self.assertEqual(conf['dir'], os.path.join(base_path, 'foo'))

    def test_site_dir_is_config_dir_fails(self):
        class Schema:
            dir = c.DocsDir()

        with self.expect_error(
            dir="The 'dir' should not be the parent directory of the config file. "
            "Use a child directory instead so that the 'dir' is a sibling of the config file."
        ):
            self.get_config(
                Schema,
                {'dir': '.'},
                config_file_path=os.path.join(os.path.abspath('.'), 'mkdocs.yml'),
            )


class ListOfPathsTest(TestCase):
    def test_valid_path(self):
        paths = [os.path.dirname(__file__)]

        class Schema:
            option = c.ListOfPaths()

        self.get_config(Schema, {'option': paths})

    def test_missing_path(self):
        paths = [os.path.join("does", "not", "exist", "i", "hope")]

        class Schema:
            option = c.ListOfPaths()

        with self.expect_error(
            option=f"The path '{paths[0]}' isn't an existing file or directory."
        ):
            self.get_config(Schema, {'option': paths})

    def test_non_path(self):
        paths = [os.path.dirname(__file__), None]

        class Schema:
            option = c.ListOfPaths()

        with self.expect_error(
            option="Expected type: <class 'str'> but received: <class 'NoneType'>"
        ):
            self.get_config(Schema, {'option': paths})

    def test_empty_list(self):
        class Schema:
            option = c.ListOfPaths()

        conf = self.get_config(Schema, {'option': []})
        self.assertEqual(conf['option'], [])

    def test_non_list(self):
        paths = os.path.dirname(__file__)

        class Schema:
            option = c.ListOfPaths()

        with self.expect_error(option="Expected a list of items, but a <class 'str'> was given."):
            self.get_config(Schema, {'option': paths})

    def test_file(self):
        paths = [__file__]

        class Schema:
            option = c.ListOfPaths()

        self.get_config(Schema, {'option': paths})

    @tempdir()
    def test_paths_localized_to_config(self, base_path):
        with open(os.path.join(base_path, 'foo'), 'w') as f:
            f.write('hi')

        class Schema:
            watch = c.ListOfPaths()

        conf = self.get_config(
            Schema,
            {'watch': ['foo']},
            config_file_path=os.path.join(base_path, 'mkdocs.yml'),
        )

        self.assertEqual(conf['watch'], [os.path.join(base_path, 'foo')])


class SiteDirTest(TestCase):
    class Schema:
        site_dir = c.SiteDir()
        docs_dir = c.Dir()

    def test_doc_dir_in_site_dir(self):
        j = os.path.join
        # The parent dir is not the same on every system, so use the actual dir name
        parent_dir = mkdocs.__file__.split(os.sep)[-3]

        test_configs = (
            {'docs_dir': j('site', 'docs'), 'site_dir': 'site'},
            {'docs_dir': 'docs', 'site_dir': '.'},
            {'docs_dir': '.', 'site_dir': '.'},
            {'docs_dir': 'docs', 'site_dir': ''},
            {'docs_dir': '', 'site_dir': ''},
            {'docs_dir': j('..', parent_dir, 'docs'), 'site_dir': 'docs'},
            {'docs_dir': 'docs', 'site_dir': '/'},
        )

        for test_config in test_configs:
            with self.subTest(test_config):
                with self.expect_error(
                    site_dir=re.compile(r"The 'docs_dir' should not be within the 'site_dir'.*")
                ):
                    self.get_config(self.Schema, test_config)

    def test_site_dir_in_docs_dir(self):
        j = os.path.join

        test_configs = (
            {'docs_dir': 'docs', 'site_dir': j('docs', 'site')},
            {'docs_dir': '.', 'site_dir': 'site'},
            {'docs_dir': '', 'site_dir': 'site'},
            {'docs_dir': '/', 'site_dir': 'site'},
        )

        for test_config in test_configs:
            with self.subTest(test_config):
                with self.expect_error(
                    site_dir=re.compile(r"The 'site_dir' should not be within the 'docs_dir'.*")
                ):
                    self.get_config(self.Schema, test_config)

    def test_common_prefix(self):
        """Legitimate settings with common prefixes should not fail validation."""

        test_configs = (
            {'docs_dir': 'docs', 'site_dir': 'docs-site'},
            {'docs_dir': 'site-docs', 'site_dir': 'site'},
        )

        for test_config in test_configs:
            with self.subTest(test_config):
                self.get_config(self.Schema, test_config)


class ThemeTest(TestCase):
    def test_theme_as_string(self):
        class Schema:
            option = c.Theme()

        conf = self.get_config(Schema, {'option': "mkdocs"})
        self.assertEqual(conf['option'].name, 'mkdocs')

    def test_uninstalled_theme_as_string(self):
        class Schema:
            option = c.Theme()

        with self.expect_error(
            option=re.compile(
                r"Unrecognised theme name: 'mkdocs2'. The available installed themes are: .+"
            )
        ):
            self.get_config(Schema, {'option': "mkdocs2"})

    def test_theme_default(self):
        class Schema:
            option = c.Theme(default='mkdocs')

        conf = self.get_config(Schema, {'option': None})
        self.assertEqual(conf['option'].name, 'mkdocs')

    def test_theme_as_simple_config(self):
        config = {
            'name': 'mkdocs',
        }

        class Schema:
            option = c.Theme()

        conf = self.get_config(Schema, {'option': config})
        self.assertEqual(conf['option'].name, 'mkdocs')

    @tempdir()
    def test_theme_as_complex_config(self, custom_dir):
        config = {
            'name': 'mkdocs',
            'custom_dir': custom_dir,
            'static_templates': ['sitemap.html'],
            'show_sidebar': False,
        }

        class Schema:
            option = c.Theme()

        conf = self.get_config(Schema, {'option': config})
        self.assertEqual(conf['option'].name, 'mkdocs')
        self.assertIn(custom_dir, conf['option'].dirs)
        self.assertEqual(
            conf['option'].static_templates,
            {'404.html', 'sitemap.xml', 'sitemap.html'},
        )
        self.assertEqual(conf['option']['show_sidebar'], False)

    def test_theme_name_is_none(self):
        config = {
            'name': None,
        }

        class Schema:
            option = c.Theme()

        with self.expect_error(option="At least one of 'name' or 'custom_dir' must be defined."):
            self.get_config(Schema, {'option': config})

    def test_theme_config_missing_name(self):
        config = {
            'custom_dir': 'custom',
        }

        class Schema:
            option = c.Theme()

        with self.expect_error(option="No theme name set."):
            self.get_config(Schema, {'option': config})

    def test_uninstalled_theme_as_config(self):
        config = {
            'name': 'mkdocs2',
        }

        class Schema:
            option = c.Theme()

        with self.expect_error(
            option=re.compile(
                r"Unrecognised theme name: 'mkdocs2'. The available installed themes are: .+"
            )
        ):
            self.get_config(Schema, {'option': config})

    def test_theme_invalid_type(self):
        config = ['mkdocs2']

        class Schema:
            option = c.Theme()

        with self.expect_error(
            option="Invalid type <class 'list'>. Expected a string or key/value pairs."
        ):
            self.get_config(Schema, {'option': config})

    def test_post_validation_none_theme_name_and_missing_custom_dir(self):
        config = {
            'theme': {
                'name': None,
            },
        }

        class Schema:
            theme = c.Theme()

        with self.expect_error(theme="At least one of 'name' or 'custom_dir' must be defined."):
            self.get_config(Schema, config)

    @tempdir()
    def test_post_validation_inexisting_custom_dir(self, abs_base_path):
        path = os.path.join(abs_base_path, 'inexisting_custom_dir')
        config = {
            'theme': {
                'name': None,
                'custom_dir': path,
            },
        }

        class Schema:
            theme = c.Theme()

        with self.expect_error(theme=f"The path set in custom_dir ('{path}') does not exist."):
            self.get_config(Schema, config)

    def test_post_validation_locale_none(self):
        config = {
            'theme': {
                'name': 'mkdocs',
                'locale': None,
            },
        }

        class Schema:
            theme = c.Theme()

        with self.expect_error(theme="'locale' must be a string."):
            self.get_config(Schema, config)

    def test_post_validation_locale_invalid_type(self):
        config = {
            'theme': {
                'name': 'mkdocs',
                'locale': 0,
            },
        }

        class Schema:
            theme = c.Theme()

        with self.expect_error(theme="'locale' must be a string."):
            self.get_config(Schema, config)

    def test_post_validation_locale(self):
        config = {
            'theme': {
                'name': 'mkdocs',
                'locale': 'fr',
            },
        }

        class Schema:
            theme = c.Theme()

        conf = self.get_config(Schema, config)
        self.assertEqual(conf['theme']['locale'].language, 'fr')


class NavTest(TestCase):
    class Schema:
        option = c.Nav()

    def test_old_format(self):
        with self.expect_error(
            option="Expected nav item to be a string or dict, got a list: ['index.md']"
        ):
            self.get_config(self.Schema, {'option': [['index.md']]})

    def test_provided_dict(self):
        conf = self.get_config(self.Schema, {'option': ['index.md', {"Page": "page.md"}]})
        self.assertEqual(conf['option'], ['index.md', {'Page': 'page.md'}])

    def test_provided_empty(self):
        conf = self.get_config(self.Schema, {'option': []})
        self.assertEqual(conf['option'], None)

    def test_normal_nav(self):
        nav_yaml = textwrap.dedent(
            '''\
            - Home: index.md
            - getting-started.md
            - User Guide:
                - Overview: user-guide/index.md
                - Installation: user-guide/installation.md
            '''
        )
        nav = yaml_load(io.StringIO(nav_yaml))

        conf = self.get_config(self.Schema, {'option': nav})
        self.assertEqual(conf['option'], nav)

    def test_invalid_type_dict(self):
        with self.expect_error(option="Expected nav to be a list, got a dict: {}"):
            self.get_config(self.Schema, {'option': {}})

    def test_invalid_type_int(self):
        with self.expect_error(option="Expected nav to be a list, got a int: 5"):
            self.get_config(self.Schema, {'option': 5})

    def test_invalid_item_int(self):
        with self.expect_error(option="Expected nav item to be a string or dict, got a int: 1"):
            self.get_config(self.Schema, {'option': [1]})

    def test_invalid_item_none(self):
        with self.expect_error(option="Expected nav item to be a string or dict, got None"):
            self.get_config(self.Schema, {'option': [None]})

    def test_invalid_children_config_int(self):
        with self.expect_error(option="Expected nav to be a list, got a int: 1"):
            self.get_config(self.Schema, {'option': [{"foo.md": [{"bar.md": 1}]}]})

    def test_invalid_children_config_none(self):
        with self.expect_error(option="Expected nav to be a list, got None"):
            self.get_config(self.Schema, {'option': [{"foo.md": None}]})

    def test_invalid_children_empty_dict(self):
        nav = ['foo', {}]
        with self.expect_error(option="Expected nav item to be a dict of size 1, got a dict: {}"):
            self.get_config(self.Schema, {'option': nav})

    def test_invalid_nested_list(self):
        nav = [{'aaa': [[{"bbb": "user-guide/index.md"}]]}]
        with self.expect_error(
            option="Expected nav item to be a string or dict, got a list: [{'bbb': 'user-guide/index.md'}]"
        ):
            self.get_config(self.Schema, {'option': nav})

    def test_invalid_children_oversized_dict(self):
        nav = [{"aaa": [{"bbb": "user-guide/index.md", "ccc": "user-guide/installation.md"}]}]
        with self.expect_error(
            option="Expected nav item to be a dict of size 1, got dict with keys ('bbb', 'ccc')"
        ):
            self.get_config(self.Schema, {'option': nav})

    def test_warns_for_dict(self):
        self.get_config(
            self.Schema,
            {'option': [{"a": {"b": "c.md", "d": "e.md"}}]},
            warnings=dict(option="Expected nav to be a list, got dict with keys ('b', 'd')"),
        )


class PrivateTest(TestCase):
    def test_defined(self):
        class Schema:
            option = c.Private()

        with self.expect_error(option="For internal use only."):
            self.get_config(Schema, {'option': 'somevalue'})


class SubConfigTest(TestCase):
    def test_subconfig_wrong_type(self):
        # Test that an error is raised if subconfig does not receive a dict
        class Schema:
            option = c.SubConfig()

        for val in "not_a_dict", ("not_a_dict",), ["not_a_dict"]:
            with self.subTest(val):
                with self.expect_error(
                    option=re.compile(
                        r"The configuration is invalid. The expected type was a key value mapping "
                        r"\(a python dict\) but we got an object of type: .+"
                    )
                ):
                    self.get_config(Schema, {'option': val})

    def test_subconfig_ignored(self):
        """Default behaviour of subconfig: validation is ignored"""

        # Nominal
        class Schema:
            option = c.SubConfig(('cc', c.Choice(('foo', 'bar'))))

        conf = self.get_config(Schema, {'option': {'cc': 'foo'}})
        self.assertEqual(conf, {'option': {'cc': 'foo'}})

        # Invalid option: No error
        class Schema:
            option = c.SubConfig(('cc', c.Choice(('foo', 'bar'))))

        conf = self.get_config(Schema, {'option': {'cc': True}})
        self.assertEqual(conf, {'option': {'cc': True}})

        # Missing option: Will be considered optional with default None
        class Schema:
            option = c.SubConfig(('cc', c.Choice(('foo', 'bar'))))

        conf = self.get_config(Schema, {'option': {}})
        self.assertEqual(conf, {'option': {'cc': None}})

        # Unknown option: No warning
        class Schema:
            option = c.SubConfig(('cc', c.Choice(('foo', 'bar'))))

        conf = self.get_config(Schema, {'option': {'unknown_key_is_ok': 0}})
        self.assertEqual(conf, {'option': {'cc': None, 'unknown_key_is_ok': 0}})

    def test_subconfig_unknown_option(self):
        class Schema:
            option = c.SubConfig(validate=True)

        conf = self.get_config(
            Schema,
            {'option': {'unknown': 0}},
            warnings=dict(option="Sub-option 'unknown': Unrecognised configuration name: unknown"),
        )
        self.assertEqual(conf['option'], {"unknown": 0})

    def test_subconfig_invalid_option(self):
        class Schema:
            option = c.SubConfig(
                ('cc', c.Choice(('foo', 'bar'))),
                validate=True,
            )

        with self.expect_error(
            option="Sub-option 'cc': Expected one of: ('foo', 'bar') but received: True"
        ):
            self.get_config(Schema, {'option': {'cc': True}})

    def test_subconfig_normal(self):
        class Schema:
            option = c.SubConfig(
                ('cc', c.Choice(('foo', 'bar'))),
            )

        conf = self.get_config(Schema, {'option': {'cc': 'foo'}})
        self.assertEqual(conf['option'], {'cc': 'foo'})


class ConfigItemsTest(TestCase):
    def test_subconfig_with_multiple_items(self):
        # This had a bug where subsequent items would get merged into the same dict.
        class Schema:
            the_items = c.ConfigItems(
                ("value", c.Type(str)),
            )

        conf = self.get_config(
            Schema,
            {
                'the_items': [
                    {'value': 'a'},
                    {'value': 'b'},
                ]
            },
        )
        self.assertEqual(conf['the_items'], [{'value': 'a'}, {'value': 'b'}])

    def test_optional(self):
        class Schema:
            sub = c.ListOfItems(
                c.SubConfig(
                    ('opt', c.Type(int)),
                    validate=True,
                ),
                default=[],
            )

        conf = self.get_config(Schema, {})
        self.assertEqual(conf['sub'], [])

        conf = self.get_config(Schema, {'sub': None})
        self.assertEqual(conf['sub'], [])

        conf = self.get_config(Schema, {'sub': [{'opt': 1}, {}]})
        self.assertEqual(conf['sub'], [{'opt': 1}, {'opt': None}])

        conf = self.get_config(Schema, {'sub': []})

        conf = self.get_config(Schema, {'sub': [{'opt': 1}, {'opt': 2}]})
        self.assertEqual(conf['sub'], [{'opt': 1}, {'opt': 2}])

    def test_required(self):
        class Schema:
            sub = c.ListOfItems(
                c.SubConfig(
                    ('opt', c.Type(int, required=True)),
                    validate=True,
                )
            )

        with self.expect_error(sub="Required configuration not provided."):
            conf = self.get_config(Schema, {})

        with self.expect_error(sub="Required configuration not provided."):
            conf = self.get_config(Schema, {'sub': None})

        with self.expect_error(
            sub="Sub-option 'opt': Expected type: <class 'int'> but received: <class 'str'>"
        ):
            conf = self.get_config(Schema, {'sub': [{'opt': 'asdf'}, {}]})

        conf = self.get_config(Schema, {'sub': []})

        conf = self.get_config(Schema, {'sub': [{'opt': 1}, {'opt': 2}]})
        self.assertEqual(conf['sub'], [{'opt': 1}, {'opt': 2}])

        with self.expect_error(
            sub="Sub-option 'opt': Expected type: <class 'int'> but received: <class 'str'>"
        ):
            self.get_config(Schema, {'sub': [{'opt': 'z'}, {'opt': 2}]})

        with self.expect_error(
            sub="Sub-option 'opt': Expected type: <class 'int'> but received: <class 'str'>"
        ):
            conf = self.get_config(Schema, {'sub': [{'opt': 'z'}, {'opt': 2}]})

        with self.expect_error(
            sub="The configuration is invalid. The expected type was a key value mapping "
            "(a python dict) but we got an object of type: <class 'int'>"
        ):
            conf = self.get_config(Schema, {'sub': [1, 2]})


class MarkdownExtensionsTest(TestCase):
    @patch('markdown.Markdown')
    def test_simple_list(self, mock_md):
        class Schema:
            markdown_extensions = c.MarkdownExtensions()
            mdx_configs = c.Private()

        config = {
            'markdown_extensions': ['foo', 'bar'],
        }
        conf = self.get_config(Schema, config)
        self.assertEqual(conf['markdown_extensions'], ['foo', 'bar'])
        self.assertEqual(conf['mdx_configs'], {})

    @patch('markdown.Markdown')
    def test_list_dicts(self, mock_md):
        class Schema:
            markdown_extensions = c.MarkdownExtensions()
            mdx_configs = c.Private()

        config = {
            'markdown_extensions': [
                {'foo': {'foo_option': 'foo value'}},
                {'bar': {'bar_option': 'bar value'}},
                {'baz': None},
            ]
        }
        conf = self.get_config(Schema, config)
        self.assertEqual(conf['markdown_extensions'], ['foo', 'bar', 'baz'])
        self.assertEqual(
            conf['mdx_configs'],
            {
                'foo': {'foo_option': 'foo value'},
                'bar': {'bar_option': 'bar value'},
            },
        )

    @patch('markdown.Markdown')
    def test_mixed_list(self, mock_md):
        class Schema:
            markdown_extensions = c.MarkdownExtensions()
            mdx_configs = c.Private()

        config = {
            'markdown_extensions': [
                'foo',
                {'bar': {'bar_option': 'bar value'}},
            ]
        }
        conf = self.get_config(Schema, config)
        self.assertEqual(conf['markdown_extensions'], ['foo', 'bar'])
        self.assertEqual(
            conf['mdx_configs'],
            {
                'bar': {'bar_option': 'bar value'},
            },
        )

    @patch('markdown.Markdown')
    def test_dict_of_dicts(self, mock_md):
        class Schema:
            markdown_extensions = c.MarkdownExtensions()
            mdx_configs = c.Private()

        config = {
            'markdown_extensions': {
                'foo': {'foo_option': 'foo value'},
                'bar': {'bar_option': 'bar value'},
                'baz': {},
            }
        }
        conf = self.get_config(Schema, config)
        self.assertEqual(conf['markdown_extensions'], ['foo', 'bar', 'baz'])
        self.assertEqual(
            conf['mdx_configs'],
            {
                'foo': {'foo_option': 'foo value'},
                'bar': {'bar_option': 'bar value'},
            },
        )

    @patch('markdown.Markdown')
    def test_builtins(self, mock_md):
        class Schema:
            markdown_extensions = c.MarkdownExtensions(builtins=['meta', 'toc'])
            mdx_configs = c.Private()

        config = {
            'markdown_extensions': ['foo', 'bar'],
        }
        conf = self.get_config(Schema, config)
        self.assertEqual(conf['markdown_extensions'], ['meta', 'toc', 'foo', 'bar'])
        self.assertEqual(conf['mdx_configs'], {})

    def test_duplicates(self):
        class Schema:
            markdown_extensions = c.MarkdownExtensions(builtins=['meta', 'toc'])
            mdx_configs = c.Private()

        config = {
            'markdown_extensions': ['meta', 'toc'],
        }
        conf = self.get_config(Schema, config)
        self.assertEqual(conf['markdown_extensions'], ['meta', 'toc'])
        self.assertEqual(conf['mdx_configs'], {})

    def test_builtins_config(self):
        class Schema:
            markdown_extensions = c.MarkdownExtensions(builtins=['meta', 'toc'])
            mdx_configs = c.Private()

        config = {
            'markdown_extensions': [
                {'toc': {'permalink': True}},
            ],
        }
        conf = self.get_config(Schema, config)
        self.assertEqual(conf['markdown_extensions'], ['meta', 'toc'])
        self.assertEqual(conf['mdx_configs'], {'toc': {'permalink': True}})

    @patch('markdown.Markdown')
    def test_configkey(self, mock_md):
        class Schema:
            markdown_extensions = c.MarkdownExtensions(configkey='bar')
            bar = c.Private()

        config = {
            'markdown_extensions': [
                {'foo': {'foo_option': 'foo value'}},
            ]
        }
        conf = self.get_config(Schema, config)
        self.assertEqual(conf['markdown_extensions'], ['foo'])
        self.assertEqual(
            conf['bar'],
            {
                'foo': {'foo_option': 'foo value'},
            },
        )

    def test_missing_default(self):
        class Schema:
            markdown_extensions = c.MarkdownExtensions()
            mdx_configs = c.Private()

        conf = self.get_config(Schema, {})
        self.assertEqual(conf['markdown_extensions'], [])
        self.assertEqual(conf['mdx_configs'], {})

    def test_none(self):
        class Schema:
            markdown_extensions = c.MarkdownExtensions(default=[])
            mdx_configs = c.Private()

        config = {
            'markdown_extensions': None,
        }
        conf = self.get_config(Schema, config)
        self.assertEqual(conf['markdown_extensions'], [])
        self.assertEqual(conf['mdx_configs'], {})

    @patch('markdown.Markdown')
    def test_not_list(self, mock_md):
        class Schema:
            option = c.MarkdownExtensions()

        with self.expect_error(option="Invalid Markdown Extensions configuration"):
            self.get_config(Schema, {'option': 'not a list'})

    @patch('markdown.Markdown')
    def test_invalid_config_option(self, mock_md):
        class Schema:
            markdown_extensions = c.MarkdownExtensions()

        config = {
            'markdown_extensions': [
                {'foo': 'not a dict'},
            ],
        }
        with self.expect_error(
            markdown_extensions="Invalid config options for Markdown Extension 'foo'."
        ):
            self.get_config(Schema, config)

    @patch('markdown.Markdown')
    def test_invalid_config_item(self, mock_md):
        class Schema:
            markdown_extensions = c.MarkdownExtensions()

        config = {
            'markdown_extensions': [
                ['not a dict'],
            ],
        }
        with self.expect_error(markdown_extensions="Invalid Markdown Extensions configuration"):
            self.get_config(Schema, config)

    @patch('markdown.Markdown')
    def test_invalid_dict_item(self, mock_md):
        class Schema:
            markdown_extensions = c.MarkdownExtensions()

        config = {
            'markdown_extensions': [
                {'key1': 'value', 'key2': 'too many keys'},
            ],
        }
        with self.expect_error(markdown_extensions="Invalid Markdown Extensions configuration"):
            self.get_config(Schema, config)

    def test_unknown_extension(self):
        class Schema:
            markdown_extensions = c.MarkdownExtensions()

        config = {
            'markdown_extensions': ['unknown'],
        }
        with self.expect_error(
            markdown_extensions=re.compile(r"Failed to load extension 'unknown'.\n.+")
        ):
            self.get_config(Schema, config)

    def test_multiple_markdown_config_instances(self):
        # This had a bug where an extension config would persist to separate
        # config instances that didn't specify extensions.
        class Schema:
            markdown_extensions = c.MarkdownExtensions()
            mdx_configs = c.Private()

        conf = self.get_config(
            Schema,
            {
                'markdown_extensions': [{'toc': {'permalink': '##'}}],
            },
        )
        self.assertEqual(conf['mdx_configs']['toc'], {'permalink': '##'})

        conf = self.get_config(
            Schema,
            {},
        )
        self.assertIsNone(conf['mdx_configs'].get('toc'))


class HooksTest(TestCase):
    class Schema:
        plugins = c.Plugins(default=[])
        hooks = c.Hooks('plugins')

    @tempdir()
    def test_hooks(self, src_dir):
        write_file(
            b'def on_page_markdown(markdown, **kwargs): return markdown.replace("f", "z")',
            os.path.join(src_dir, 'hooks', 'my_hook.py'),
        )
        write_file(
            b'foo foo',
            os.path.join(src_dir, 'docs', 'index.md'),
        )
        conf = self.get_config(
            self.Schema,
            {'hooks': ['hooks/my_hook.py']},
            config_file_path=os.path.join(src_dir, 'mkdocs.yml'),
        )
        self.assertIn('hooks/my_hook.py', conf['plugins'])
        hook = conf['plugins']['hooks/my_hook.py']
        self.assertTrue(hasattr(hook, 'on_page_markdown'))
        self.assertEqual(
            {**conf['plugins'].events, 'page_markdown': [hook.on_page_markdown]},
            conf['plugins'].events,
        )
        self.assertEqual(hook.on_page_markdown('foo foo'), 'zoo zoo')
        self.assertFalse(hasattr(hook, 'on_nav'))


class SchemaTest(TestCase):
    def test_copy(self):
        copy.deepcopy(
            base.LegacyConfig(
                (('foo', c.MarkdownExtensions()),),
            ),
        )

        copy.deepcopy(self.get_config(IpAddressTest.Schema, {'option': '1.2.3.4:5678'}))
        copy.deepcopy(IpAddressTest.Schema)
        copy.deepcopy(base.get_schema(IpAddressTest.Schema))

        copy.deepcopy(self.get_config(EditURITest.Schema, {}))
        copy.deepcopy(EditURITest.Schema)
        copy.deepcopy(base.get_schema(EditURITest.Schema))
