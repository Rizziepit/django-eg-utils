from django.conf import settings
from django.db import models

from git import Repo

from egutils import utils


'''
TODO: create a model which stores links to admin pages
for display on the admin home page or in a special section.
Then a link directly to the form page in EGModelConfiguration
can be pinned on the admin home page.
'''


class EGModelConfiguration(models.Model):
    '''
    This model stores configurations for elastic-git models found in
    the project repo. For now the configuration consists only of a
    `forms_builder.forms.models.Form` object which specifies a form
    which will be used to edit model objects.
    '''
    schema = models.CharField(
        unique=True,
        choices=[
            (ct, ct) for ct
            in utils.list_content_types(Repo(settings.GIT_REPO_PATH))],
        max_length=255
    )
    form = models.ForeignKey('forms.Form')

    class Meta:
        verbose_name = 'EG Model Configuration'

    def form_for_model(self):
        '''
        TODO: construct self.form with initial fields and options
        based on the model.
        '''
        model = utils.load_model_class(
            Repo(settings.GIT_REPO_PATH), self.schema)


'''
DISCUSSION

The concept of storing form fields and options, e.g. choices, help text, etc.,
in a model will allow customized `EGModelForm` instances to be created.

A `forms_builder.forms.models.Form` object won't suffice as the form options
model because it generates a normal Django form and doesn't allow
`ModelForm` fields like `ModelChoiceField`. Additionally, saving that form
data to an EG model object will be very error-prone.

A better plan might be to extend `forms_builder.forms.models.Form`
and related models to generate instances of `EGModelForm` instead.
'''
