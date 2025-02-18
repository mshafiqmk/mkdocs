import os
import unittest

from mkdocs import exceptions
from mkdocs.config import base
from mkdocs.config import config_options as c
from mkdocs.config import defaults
from mkdocs.config.base import ValidationError
from mkdocs.tests.base import change_dir, tempdir


class ConfigBaseTests(unittest.TestCase):
    def test_unrecognised_keys(self):
        conf = defaults.MkDocsConfig()
        conf.load_dict(
            {
                'not_a_valid_config_option': "test",
            }
        )

        failed, warnings = conf.validate()

        self.assertEqual(
            warnings,
            [
                (
                    'not_a_valid_config_option',
                    'Unrecognised configuration name: not_a_valid_config_option',
                )
            ],
        )

    def test_missing_required(self):
        conf = defaults.MkDocsConfig()

        errors, warnings = conf.validate()

        self.assertEqual(
            errors, [('site_name', ValidationError('Required configuration not provided.'))]
        )
        self.assertEqual(warnings, [])

    @tempdir()
    def test_load_from_file(self, temp_dir):
        """
        Users can explicitly set the config file using the '--config' option.
        Allows users to specify a config other than the default `mkdocs.yml`.
        """
        with open(os.path.join(temp_dir, 'mkdocs.yml'), 'w') as config_file:
            config_file.write("site_name: MkDocs Test\n")
        os.mkdir(os.path.join(temp_dir, 'docs'))

        cfg = base.load_config(config_file=config_file.name)
        self.assertTrue(isinstance(cfg, defaults.MkDocsConfig))
        self.assertEqual(cfg['site_name'], 'MkDocs Test')

    @tempdir()
    def test_load_default_file(self, temp_dir):
        """
        test that `mkdocs.yml` will be loaded when '--config' is not set.
        """
        with open(os.path.join(temp_dir, 'mkdocs.yml'), 'w') as config_file:
            config_file.write("site_name: MkDocs Test\n")
        os.mkdir(os.path.join(temp_dir, 'docs'))
        with change_dir(temp_dir):
            cfg = base.load_config(config_file=None)
            self.assertTrue(isinstance(cfg, defaults.MkDocsConfig))
            self.assertEqual(cfg['site_name'], 'MkDocs Test')

    @tempdir
    def test_load_default_file_with_yaml(self, temp_dir):
        """
        test that `mkdocs.yml` will be loaded when '--config' is not set.
        """
        with open(os.path.join(temp_dir, 'mkdocs.yaml'), 'w') as config_file:
            config_file.write("site_name: MkDocs Test\n")
        os.mkdir(os.path.join(temp_dir, 'docs'))
        with change_dir(temp_dir):
            cfg = base.load_config(config_file=None)
            self.assertTrue(isinstance(cfg, defaults.MkDocsConfig))
            self.assertEqual(cfg['site_name'], 'MkDocs Test')

    @tempdir()
    def test_load_default_file_prefer_yml(self, temp_dir):
        """
        test that `mkdocs.yml` will be loaded when '--config' is not set.
        """
        with open(os.path.join(temp_dir, 'mkdocs.yml'), 'w') as config_file1:
            config_file1.write("site_name: MkDocs Test1\n")
        with open(os.path.join(temp_dir, 'mkdocs.yaml'), 'w') as config_file2:
            config_file2.write("site_name: MkDocs Test2\n")

        os.mkdir(os.path.join(temp_dir, 'docs'))
        with change_dir(temp_dir):
            cfg = base.load_config(config_file=None)
            self.assertTrue(isinstance(cfg, defaults.MkDocsConfig))
            self.assertEqual(cfg['site_name'], 'MkDocs Test1')

    def test_load_from_missing_file(self):
        with self.assertRaisesRegex(
            exceptions.ConfigurationError, "Config file 'missing_file.yml' does not exist."
        ):
            base.load_config(config_file='missing_file.yml')

    @tempdir()
    def test_load_from_open_file(self, temp_path):
        """
        `load_config` can accept an open file descriptor.
        """
        config_fname = os.path.join(temp_path, 'mkdocs.yml')
        config_file = open(config_fname, 'w+')
        config_file.write("site_name: MkDocs Test\n")
        config_file.flush()
        os.mkdir(os.path.join(temp_path, 'docs'))

        cfg = base.load_config(config_file=config_file)
        self.assertTrue(isinstance(cfg, defaults.MkDocsConfig))
        self.assertEqual(cfg['site_name'], 'MkDocs Test')
        # load_config will always close the file
        self.assertTrue(config_file.closed)

    @tempdir()
    def test_load_from_closed_file(self, temp_dir):
        """
        The `serve` command with auto-reload may pass in a closed file descriptor.
        Ensure `load_config` reloads the closed file.
        """
        with open(os.path.join(temp_dir, 'mkdocs.yml'), 'w') as config_file:
            config_file.write("site_name: MkDocs Test\n")
        os.mkdir(os.path.join(temp_dir, 'docs'))

        cfg = base.load_config(config_file=config_file)
        self.assertTrue(isinstance(cfg, defaults.MkDocsConfig))
        self.assertEqual(cfg['site_name'], 'MkDocs Test')

    @tempdir
    def test_load_missing_required(self, temp_dir):
        """
        `site_name` is a required setting.
        """
        with open(os.path.join(temp_dir, 'mkdocs.yml'), 'w') as config_file:
            config_file.write("site_dir: output\nsite_url: https://www.mkdocs.org\n")
        os.mkdir(os.path.join(temp_dir, 'docs'))

        with self.assertLogs('mkdocs') as cm:
            with self.assertRaises(exceptions.Abort):
                base.load_config(config_file=config_file.name)
        self.assertEqual(
            '\n'.join(cm.output),
            "ERROR:mkdocs.config:Config value 'site_name': Required configuration not provided.",
        )

    def test_pre_validation_error(self):
        class InvalidConfigOption(c.BaseConfigOption):
            def pre_validation(self, config, key_name):
                raise ValidationError('pre_validation error')

        conf = base.Config(schema=(('invalid_option', InvalidConfigOption()),))

        errors, warnings = conf.validate()

        self.assertEqual(errors, [('invalid_option', ValidationError('pre_validation error'))])
        self.assertEqual(warnings, [])

    def test_run_validation_error(self):
        class InvalidConfigOption(c.BaseConfigOption):
            def run_validation(self, value):
                raise ValidationError('run_validation error')

        conf = base.Config(schema=(('invalid_option', InvalidConfigOption()),))

        errors, warnings = conf.validate()

        self.assertEqual(errors, [('invalid_option', ValidationError('run_validation error'))])
        self.assertEqual(warnings, [])

    def test_post_validation_error(self):
        class InvalidConfigOption(c.BaseConfigOption):
            def post_validation(self, config, key_name):
                raise ValidationError('post_validation error')

        conf = base.Config(schema=(('invalid_option', InvalidConfigOption()),))

        errors, warnings = conf.validate()

        self.assertEqual(errors, [('invalid_option', ValidationError('post_validation error'))])
        self.assertEqual(warnings, [])

    def test_pre_and_run_validation_errors(self):
        """A pre_validation error does not stop run_validation from running."""

        class InvalidConfigOption(c.BaseConfigOption):
            def pre_validation(self, config, key_name):
                raise ValidationError('pre_validation error')

            def run_validation(self, value):
                raise ValidationError('run_validation error')

        conf = base.Config(schema=(('invalid_option', InvalidConfigOption()),))

        errors, warnings = conf.validate()

        self.assertEqual(
            errors,
            [
                ('invalid_option', ValidationError('pre_validation error')),
                ('invalid_option', ValidationError('run_validation error')),
            ],
        ),
        self.assertEqual(warnings, [])

    def test_run_and_post_validation_errors(self):
        """A run_validation error stops post_validation from running."""

        class InvalidConfigOption(c.BaseConfigOption):
            def run_validation(self, value):
                raise ValidationError('run_validation error')

            def post_validation(self, config, key_name):
                raise ValidationError('post_validation error')

        conf = base.Config(schema=(('invalid_option', InvalidConfigOption()),))

        errors, warnings = conf.validate()

        self.assertEqual(errors, [('invalid_option', ValidationError('run_validation error'))])
        self.assertEqual(warnings, [])

    def test_validation_warnings(self):
        class InvalidConfigOption(c.BaseConfigOption):
            def pre_validation(self, config, key_name):
                self.warnings.append('pre_validation warning')

            def run_validation(self, value):
                self.warnings.append('run_validation warning')

            def post_validation(self, config, key_name):
                self.warnings.append('post_validation warning')

        conf = base.Config(schema=(('invalid_option', InvalidConfigOption()),))

        errors, warnings = conf.validate()

        self.assertEqual(errors, [])
        self.assertEqual(
            warnings,
            [
                ('invalid_option', 'pre_validation warning'),
                ('invalid_option', 'run_validation warning'),
                ('invalid_option', 'post_validation warning'),
            ],
        )

    @tempdir()
    def test_load_from_file_with_relative_paths(self, config_dir):
        """
        When explicitly setting a config file, paths should be relative to the
        config file, not the working directory.
        """
        config_fname = os.path.join(config_dir, 'mkdocs.yml')
        with open(config_fname, 'w') as config_file:
            config_file.write("docs_dir: src\nsite_name: MkDocs Test\n")
        docs_dir = os.path.join(config_dir, 'src')
        os.mkdir(docs_dir)

        cfg = base.load_config(config_file=config_file)
        self.assertTrue(isinstance(cfg, defaults.MkDocsConfig))
        self.assertEqual(cfg['site_name'], 'MkDocs Test')
        self.assertEqual(cfg['docs_dir'], docs_dir)
        self.assertEqual(cfg.config_file_path, config_fname)
        self.assertIsInstance(cfg.config_file_path, str)

    def test_get_schema(self):
        class FooConfig:
            z = c.URL()
            aa = c.Type(int)

        self.assertEqual(
            base.get_schema(FooConfig),
            (
                ('z', FooConfig.z),
                ('aa', FooConfig.aa),
            ),
        )
