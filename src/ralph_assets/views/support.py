# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from bob.djid import Djid

from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.translation import ugettext_lazy as _

from ralph.account.models import Perm, ralph_permission
from ralph_assets.forms_support import (
    AddSupportForm,
    EditSupportForm,
)
from ralph_assets.models_assets import Asset
from ralph_assets.models_support import Support
from ralph_assets.views.base import AssetsBase
from ralph_assets.views.search import DjidView


class SupportView(AssetsBase):
    """Base view that displays support form."""

    submodule_name = 'supports'
    template_name = 'assets/add_support.html'
    mainmenu_selected = 'supports'
    sidebar_selected = None

    def _get_form(self, data=None, **kwargs):
        self.form = self.form_class(
            data=data, **kwargs
        )

    def get_context_data(self, **kwargs):
        ret = super(SupportView, self).get_context_data(**kwargs)
        ret.update({
            'form': self.form,
            'form_id': 'add_support_form',
            'edit_mode': False,
            'caption': self.caption,
            'support': getattr(self, 'support', None),
            'assets_disabled': getattr(settings, 'ASSETS_DISABLED', False)
        })
        return ret

    def _save(self, request, *args, **kwargs):
        try:
            support = self.form.save(commit=False)
            support.save(user=self.request.user)
            self.form.save_m2m()
            messages.success(self.request, self.message)
            return HttpResponseRedirect(support.get_absolute_url())
        except ValueError:
            return super(SupportView, self).get(request, *args, **kwargs)


class AddSupportView(SupportView):
    """Add a new support"""
    caption = _('Add Support')
    message = _('Support added')
    active_sidebar_item = 'add support'

    def __init__(self, *args, **kwargs):
        self.form_class = AddSupportForm
        super(AddSupportView, self).__init__(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        self._get_form()
        return super(AddSupportView, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self._get_form(request.POST)
        if self.form.is_valid():
            self.form.instance.pk = None
            support = self.form.save(commit=False)
            support.save(user=self.request.user)
            messages.success(self.request, self.message)
            return HttpResponseRedirect(
                reverse('edit_support', kwargs={'support_id': support.pk}),
            )
        else:
            return super(AddSupportView, self).get(request, *args, **kwargs)


class SupportListDjid(Djid):
    """The grid with support list"""

    @classmethod
    def view_decorator(cls, view):
        perms = [
            {
                'perm': Perm.has_assets_access,
                'msg': _("You don't have permission to see Assets."),
            },
        ]
        return ralph_permission(perms)(view)

    class Meta:
        Model = Support
        columns = [
            'support_type',
            'contract_id',
            'name',
            'serial_no',
            'date_from',
            'date_to',
            'price',
            'created',
            'additional_notes',
            'description',
        ]
        djid_id = 'support-list'

        additional_params = {
            'height': 465,
            'autowidth': True,
            'scroll': False,
            'multiselect': True,
        }


class SupportList(DjidView, AssetsBase):
    """The support list."""

    submodule_name = 'supports'
    DjidClass = SupportListDjid


class EditSupportView(SupportView):
    """Edit support"""
    caption = _('Edit Support')
    message = _('Support changed')
    submodule_name = 'supports'
    Form = EditSupportForm
    detect_changes = True

    def __init__(self, *args, **kwargs):
        self.form_class = EditSupportForm
        super(EditSupportView, self).__init__(*args, **kwargs)

    def get(self, request, support_id, *args, **kwargs):
        self.support = get_object_or_404(Support, pk=support_id)
        self._get_form(instance=self.support)
        return super(EditSupportView, self).get(request, *args, **kwargs)

    def post(self, request, support_id, *args, **kwargs):
        self.support = Support.objects.get(pk=support_id)
        self._get_form(request.POST, instance=self.support)
        return self._save(request, *args, **kwargs)


class DeleteSupportView(AssetsBase):
    """Delete a support."""
    submodule_name = 'supports'

    def post(self, *args, **kwargs):
        record_id = self.request.POST.get('record_id')
        self.back_to = reverse('support_list')
        try:
            support = Support.objects.get(pk=record_id)
        except Asset.DoesNotExist:
            messages.error(self.request, _("Selected asset doesn't exists."))
            return HttpResponseRedirect(self.back_to)
        support.delete(user=self.request.user)
        return HttpResponseRedirect(self.back_to)
