'''
This module contains the base class for elastic-git model forms, EGModelForm.
It works the same as ModelForm and provides the same Meta options. However, it
only works for models with simple fields at the moment, i.e. not
`elasticgit.models.ListField` and `elasticgit.models.DictField`.

Adapted from Django ModelForm code:
https://github.com/django/django/blob/1.6.10/django/forms/models.py

TODO list for a complete solution:

* matching form fields for `elasticgit.models.ListField` and
    `elasticgit.models.DictField`.
* a subclass of ModelChoiceField that allows selection of either
    Django or elastic-git model instances, and serializes these
    to a UUID hex string.
* a subclass of ModelMultipleChoiceField that implements a ListField interface.
    It allows selection of either Django or elastic-git model instances, and
    serializes these to a list of UUID hex strings.
* detect TextField fields that contain datetime strings and use a DateTimeInput
    widget for these instead (elastic-git has no DateTimeField equivalent).
* detect datetime fields with names like "modified", "last_updated", etc. which
    must be auto-updated to the current time on form save.
* add a form factory function so that forms can be created on the fly by views,
    based on Django's modelform_factory:
    https://docs.djangoproject.com/en/1.6/ref/forms/models/#django.forms.models.modelform_factory

CHALLENGES:

elastic-git fields don't have the attribute `choices`. So it isn't possible
to generate selection options automatically based on a model. These choices
have to be specified somewhere, e.g. an EGModelForm subclass or in the factory
function arguments. We need a way of configuring form options without
writing code. This also applies to a number of other form customizations.
'''
from collections import OrderedDict

import six

from django import forms
from django.forms.util import ErrorList
from django.core.exceptions import (
    ImproperlyConfigured, FieldError)
from django.forms.forms import BaseForm, get_declared_fields
from django.forms.models import ModelFormOptions, ALL_FIELDS
from django.forms.widgets import media_property

from elasticgit import models as eg_models


FIELD_MAPPING = {
    eg_models.UUIDField: forms.CharField,
    eg_models.TextField: forms.CharField,
    eg_models.UnicodeTextField: forms.CharField,
    eg_models.IntegerField: forms.IntegerField,
    eg_models.FloatField: forms.FloatField,
    eg_models.BooleanField: forms.BooleanField,
    eg_models.ListField: forms.CharField,  # TODO: this won't validate
    eg_models.DictField: forms.CharField,  # TODO: this won't validate
    eg_models.URLField: forms.URLField
}
# TODO: auto-update DateTimeField (but EG uses a TextField for those)
EXCLUDED_FIELDS = ('_version', 'uuid', 'id')


def fields_for_model(model, fields, exclude, widgets, localized_fields, labels,
                     help_texts, error_messages):
    """
    Returns a ``OrderedDict`` containing form fields for the given model.

    ``fields`` is an optional list of field names. If provided, only the named
    fields will be included in the returned fields.

    ``exclude`` is an optional list of field names. If provided, the named
    fields will be excluded from the returned fields, even if they are listed
    in the ``fields`` argument.

    ``widgets`` is a dictionary of model field names mapped to a widget.

    ``localized_fields`` is a list of names of fields which should be localized.

    ``labels`` is a dictionary of model field names mapped to a label.

    ``help_texts`` is a dictionary of model field names mapped to a help text.

    ``error_messages`` is a dictionary of model field names mapped to a
    dictionary of error messages.
    """
    field_list = []
    for f in model._get_fields():
        if f.name in EXCLUDED_FIELDS:
            continue
        if fields is not None and f.name not in fields:
            continue
        if exclude and f.name in exclude:
            continue

        kwargs = {}
        if widgets and f.name in widgets:
            kwargs['widget'] = widgets[f.name]
        if localized_fields == ALL_FIELDS or (localized_fields and f.name in localized_fields):
            kwargs['localize'] = True
        if labels and f.name in labels:
            kwargs['label'] = labels[f.name]
        if help_texts and f.name in help_texts:
            kwargs['help_text'] = help_texts[f.name]
        elif f.doc:
            kwargs['help_text'] = f.doc
        if error_messages and f.name in error_messages:
            kwargs['error_messages'] = error_messages[f.name]
        kwargs['required'] = f.required

        form_class = FIELD_MAPPING[type(f)]
        formfield = form_class(**kwargs)
        field_list.append((f.name, formfield))
    field_dict = OrderedDict(field_list)
    if fields:
        # re-order to match ordering in fields
        field_dict = OrderedDict(
            [(f, field_dict.get(f)) for f in fields
                if ((not exclude) or (exclude and f not in exclude))]
        )
    return field_dict


def model_to_dict(model, fields, exclude):
    """
    Returns a dict containing the data in ``instance`` suitable for passing as
    a Form's ``initial`` keyword argument.

    ``fields`` is an optional list of field names. If provided, only the named
    fields will be included in the returned dict.

    ``exclude`` is an optional list of field names. If provided, the named
    fields will be excluded from the returned dict, even if they are listed in
    the ``fields`` argument.
    """
    data = {}
    for f in model._get_fields():
        if f.name in EXCLUDED_FIELDS:
            continue
        if fields is not None and f.name not in fields:
            continue
        if exclude and f.name in exclude:
            continue
        data[f.name] = getattr(model, f.name)
    return data


def construct_instance(form, instance, fields=None, exclude=None):
    """
    Constructs and returns a model instance from the bound ``form``'s
    ``cleaned_data``, but does not save the returned instance.
    """
    cleaned_data = form.cleaned_data
    data = {}
    for f in instance._get_fields():
        if f.name in EXCLUDED_FIELDS:
            continue
        if fields is not None and f.name not in fields:
            continue
        if exclude and f.name in exclude:
            continue
        data[f.name] = cleaned_data[f.name]

    return instance.update(data)


class ModelFormMetaclass(type):
    def __new__(mcs, name, bases, attrs):
        declared_fields = get_declared_fields(bases, attrs, False)
        new_class = super(ModelFormMetaclass, mcs).__new__(mcs, name, bases, attrs)

        if bases == (BaseEGModelForm,):
            return new_class

        if 'media' not in attrs:
            new_class.media = media_property(new_class)
        opts = new_class._meta = ModelFormOptions(getattr(new_class, 'Meta', None))

        if opts.model:
            # If a model is defined, extract form fields from it.
            if opts.fields is None and opts.exclude is None:
                raise ImproperlyConfigured(
                    "Creating a ModelForm without either the 'fields' attribute "
                    "or the 'exclude' attribute is prohibited; form %s "
                    "needs updating." % name
                )

            if opts.fields == ALL_FIELDS:
                # Sentinel for fields_for_model to indicate "get the list of
                # fields from the model"
                opts.fields = None

            fields = fields_for_model(opts.model, opts.fields, opts.exclude,
                                      opts.widgets, opts.localized_fields,
                                      opts.labels, opts.help_texts,
                                      opts.error_messages)

            # make sure opts.fields doesn't specify an invalid field
            none_model_fields = [k for k, v in six.iteritems(fields) if not v]
            missing_fields = (set(none_model_fields) -
                              set(declared_fields.keys()))
            if missing_fields:
                message = 'Unknown field(s) (%s) specified for %s'
                message = message % (', '.join(missing_fields),
                                     opts.model.__name__)
                raise FieldError(message)
            # Override default model fields with any custom declared ones
            # (plus, include all the other declared fields).
            fields.update(declared_fields)
        else:
            fields = declared_fields

        new_class.base_fields = fields
        new_class.declared_fields = declared_fields
        return new_class


class BaseEGModelForm(BaseForm):
    '''
    Adapted from Django BaseModelForm code:
    https://github.com/django/django/blob/8656cfc4e01332426e5e4b78c20a4e9ec443b293/django/forms/models.py#L269
    '''
    def __init__(self, data=None, files=None, auto_id='id_%s', prefix=None,
                 initial=None, error_class=ErrorList, label_suffix=None,
                 empty_permitted=False, instance=None):
        opts = self._meta
        if opts.model is None:
            raise ValueError('EGModelForm has no model class specified.')
        if instance is None:
            # if we didn't get an instance, instantiate a new one
            self.instance = opts.model()
            object_data = {}
        else:
            self.instance = instance
            object_data = model_to_dict(instance, opts.fields, opts.exclude)
        # if initial was provided, it should override the values from instance
        if initial is not None:
            object_data.update(initial)
        super(BaseEGModelForm, self).__init__(data, files, auto_id, prefix, object_data,
                                              error_class, label_suffix, empty_permitted)
        # Apply ``limit_choices_to`` to each field.
        for field_name in self.fields:
            formfield = self.fields[field_name]
            if hasattr(formfield, 'queryset') and hasattr(formfield, 'get_limit_choices_to'):
                limit_choices_to = formfield.get_limit_choices_to()
                if limit_choices_to is not None:
                    formfield.queryset = formfield.queryset.complex_filter(limit_choices_to)

    def _get_validation_exclusions(self):
        """
        For backwards-compatibility, several types of fields need to be
        excluded from model validation. See the following tickets for
        details: #12507, #12521, #12553
        """
        exclude = []
        # Build up a list of fields that should be excluded from model field
        # validation and unique checks.
        for f in self.instance._get_fields():
            field = f.name
            # Exclude fields that aren't on the form. The developer may be
            # adding these values to the model after form validation.
            if field not in self.fields:
                exclude.append(f.name)

            # Don't perform model validation on fields that were defined
            # manually on the form and excluded via the ModelForm's Meta
            # class. See #12901.
            elif self._meta.fields and field not in self._meta.fields:
                exclude.append(f.name)
            elif self._meta.exclude and field in self._meta.exclude:
                exclude.append(f.name)

            # Exclude fields that failed form validation. There's no need for
            # the model fields to validate them as well.
            elif field in self._errors.keys():
                exclude.append(f.name)

        return exclude

    def clean(self):
        return self.cleaned_data

    def _post_clean(self):
        opts = self._meta
        exclude = self._get_validation_exclusions()
        # Update the model instance with self.cleaned_data.
        self.instance = construct_instance(self, self.instance, opts.fields, exclude)

    def save(self, commit=True, workspace=None, message=None, author=None,
             committer=None):
        """
        Save this form's self.instance object if commit=True. Return
        the model instance.
        """
        if self.errors:
            raise ValueError(
                "The %s could not be %s because the data didn't validate." % (
                    self.instance.__class__.__name__,
                    'updated' if self.instance.uuid else 'created',
                )
            )
        if commit:
            # If committing, save the instance immediately.
            if workspace is None:
                raise ValueError('Workspace was not provided.')
            message = message or '%s %s' % (
                self.instance.__class__.__name__,
                'updated' if self.instance.uuid else 'created')
            workspace.save(self.instance, message, author, committer)

        return self.instance

    save.alters_data = True


class EGModelForm(six.with_metaclass(ModelFormMetaclass, BaseEGModelForm)):
    pass
