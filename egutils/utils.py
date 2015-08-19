'''
These utility functions were copied from unicore.distribute.
https://github.com/universalcore/unicore.distribute/blob/develop/unicore/distribute/utils.py
'''
import os
import glob

import avro.schema

from elasticgit.commands.avro import deserialize


def list_content_types(repo):
    """
    Return a list of content types in a repository.

    :param Repo repo:
        The git repository.
    :returns: list
    """
    schema_files = glob.glob(
        os.path.join(repo.working_dir, '_schemas', '*.avsc'))
    return [os.path.splitext(os.path.basename(schema_file))[0]
            for schema_file in schema_files]


def get_schema(repo, content_type):
    """
    Return a schema for a content type in a repository.

    :param Repo repo:
        The git repository.
    :returns: dict
    """
    try:
        with open(
                os.path.join(repo.working_dir,
                             '_schemas',
                             '%s.avsc' % (content_type,)), 'r') as fp:
            data = fp.read()
            return avro.schema.parse(data)
    except IOError:  # pragma: no cover
        raise ValueError('Schema does not exist')


def load_model_class(repo, content_type):
    """
    Return a model class for a content type in a repository.

    :param Repo repo:
        The git repository.
    :param str content_type:
        The content type to list
    :returns: class
    """
    schema = get_schema(repo, content_type).to_json()
    return deserialize(schema, module_name=schema['namespace'])
