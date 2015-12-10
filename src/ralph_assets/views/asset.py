# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import logging

from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db import transaction
from django.forms.models import modelformset_factory
from django.http import HttpResponseRedirect
from django.utils.translation import ugettext_lazy as _

from ralph_assets.licences.models import Licence
from ralph_assets.forms import BladeSystemForm, BladeServerForm
from ralph_assets.models import Asset
from ralph_assets.models_assets import AssetType, DeviceInfo
from ralph_assets.views.base import (
    ActiveSubmoduleByAssetMixin,
    AssetsBase,
    BulkEditBase,
    HardwareModeMixin,
    SubmoduleModeMixin,
    get_return_link,
)
from ralph_assets.views.search import _AssetSearch, AssetSearchDataTable
from ralph_assets.views.utils import (
    _move_data,
    _update_office_info,
    get_transition_url,
)
from ralph.util.reports import Report


logger = logging.getLogger(__name__)


class DeleteAsset(AssetsBase):
    submodule_name = 'hardware'

    def post(self, *args, **kwargs):
        record_id = self.request.POST.get('record_id')
        try:
            self.asset = Asset.objects.get(
                pk=record_id
            )
        except Asset.DoesNotExist:
            messages.error(
                self.request, _("Selected asset doesn't exists.")
            )
            return HttpResponseRedirect(get_return_link(self.mode))
        else:
            if self.asset.type < AssetType.BO:
                self.back_to = '/assets/dc/'
            else:
                self.back_to = '/assets/back_office/'
            if self.asset.has_parts():
                parts = self.asset.get_parts_info()
                messages.error(
                    self.request,
                    _("Cannot remove asset with parts assigned. Please remove "
                        "or unassign them from device first. ".format(
                            self.asset,
                            ", ".join([str(part.asset) for part in parts])
                        ))
                )
                return HttpResponseRedirect(
                    '{}{}{}'.format(
                        self.back_to, 'edit/device/', self.asset.id,
                    )
                )
            # changed from softdelete to real-delete, because of
            # key-constraints issues (sn/barcode) - to be resolved.
            self.asset.delete_with_info()
            return HttpResponseRedirect(self.back_to)


class AssetSearch(Report, HardwareModeMixin, AssetSearchDataTable):
    """The main-screen search form for all type of assets."""
    active_sidebar_item = 'search'

    @property
    def submodule_name(self):
        return 'hardware'

    def get_context_data(self, *args, **kwargs):
        context = super(AssetSearch, self).get_context_data(*args, **kwargs)
        context.update({
            'url_query': self.request.GET,
            'assets_disabled': getattr(settings, 'ASSETS_DISABLED', False)
        })
        return context


class AssetBulkEdit(
    HardwareModeMixin,
    ActiveSubmoduleByAssetMixin,
    BulkEditBase,
    _AssetSearch,
):
    model = Asset
    commit_on_valid = False

    def get_object_class(self):
        return self.model

    def get_context_data(self, *args, **kwargs):
        data = super(AssetBulkEdit, self).get_context_data(*args, **kwargs)
        data['assets'] = self.get_queryset()
        return data

    def initial_forms(self, formset, queryset):
        for idx, asset in enumerate(queryset):
            if asset.office_info:
                for field in ['purpose']:
                    if field not in formset.forms[idx].fields:
                        continue
                    formset.forms[idx].fields[field].initial = (
                        getattr(asset.office_info, field, None)
                    )
            self._initialize_licences(formset.forms[idx], asset)

    def _initialize_licences(self, form, asset):
        licences_ids = asset.licences.values_list('id', flat=True)
        if licences_ids:
            form.fields['licences'].initial = licences_ids

    def _save_licences(self, asset, form):
        asset.licences.clear()
        licence_ids = form.cleaned_data.get('licences', [])
        licences = Licence.objects.filter(id__in=licence_ids)
        for licence in licences:
            licence.assign(asset)
            licence.save()

    def _get_formset_idx(self, formset, instance):
        for idx, form in enumerate(formset.forms):
            if int(formset.forms[idx]['id'].value()) == instance.id:
                break
        return idx

    def save_formset(self, instances, formset):
        with transaction.commit_on_success():
            for instance in instances:
                idx = self._get_formset_idx(formset, instance)
                instance.modified_by = self.request.user.get_profile()
                self._save_licences(instance, formset.forms[idx])
                instance.save(user=self.request.user)
                new_src, office_info_data = _move_data(
                    formset.forms[idx].cleaned_data,
                    {}, ['purpose']
                )
                formset.forms[idx].cleaned_data = new_src
                instance = _update_office_info(
                    self.request.user, instance,
                    office_info_data,
                )

    def handle_formset_error(self, formset_error):
        messages.error(
            self.request,
            _(('Please correct errors and check both "serial numbers" and '
               '"barcodes" for duplicates'))
        )

    def get_success_url(self):
        """Redirect after successfully send formset.

        :return: returns URL (``str``)
        """
        assets_ids = self.get_items_ids()
        transition_type = self.request.POST.get('transition_type')
        success_url = (
            get_transition_url(transition_type, assets_ids, self.mode) or
            super(AssetBulkEdit, self).get_success_url()
        )
        return success_url


class ChassisBulkEdit(SubmoduleModeMixin, HardwareModeMixin, AssetsBase):
    template_name = 'assets/data_center_location.html'
    SAME_SLOT_MSG_ERROR = _('Slot number must be unique')

    def get_formset(self):
        return modelformset_factory(DeviceInfo, form=BladeServerForm, extra=0)

    def get_context_data(self, *args, **kwargs):
        self.mode = 'dc'
        context = super(ChassisBulkEdit, self).get_context_data(
            *args, **kwargs
        )
        return context

    def _get_invalid_url(self, selected_ids):
        asset_search_url = reverse('asset_search', args=(self.mode,))
        url_query = 'id={}'.format(','.join(selected_ids))
        invalid_url = '{}?{}'.format(asset_search_url, url_query)
        return invalid_url

    def get(self, *args, **kwargs):
        self.selected_servers = self.request.GET.getlist('select')
        if not self.selected_servers:
            msg = _("Select at least one asset, please")
            messages.info(self.request, msg)
            return HttpResponseRedirect(reverse('dc'))

        non_blades = self._find_non_blades(
            Asset.objects.filter(pk__in=self.selected_servers)
        )
        if non_blades:
            msg_sn, msg_barcode = self._get_non_blade_message(non_blades)
            messages.error(self.request, msg_sn)
            messages.error(self.request, msg_barcode)
            return HttpResponseRedirect(
                self._get_invalid_url(self.selected_servers)
            )
        context = self.get_context_data(self, *args, **kwargs)
        context['chassis_form'] = BladeSystemForm()
        device_infos = DeviceInfo.objects.filter(
            asset__id__in=self.selected_servers
        )
        context['blade_server_formset'] = self.get_formset()(
            queryset=device_infos,
        )
        return self.render_to_response(context)

    def validate_same_slot(self, formset):
        """Checks if there was duplicated slot-number among forms."""
        def find_duplicates(formset):
            slot_no2form_ids = defaultdict(list)
            for idx, form in enumerate(formset.forms):
                slot_no = form.cleaned_data['slot_no']
                slot_no2form_ids[slot_no].append(idx)
            return slot_no2form_ids

        found_duplicates = find_duplicates(formset)
        is_valid = True
        for duplicates in found_duplicates.values():
            # add error msg to all slot-numbers in formset which are
            # duplicated
            if len(duplicates) > 1:
                for form_idx in duplicates:
                    is_valid = False
                    formset.forms[form_idx].errors['slot_no'] = (
                        self.SAME_SLOT_MSG_ERROR
                    )
        return is_valid

    def _find_non_blades(self, assets):
        non_blades = []
        for asset in assets:
            is_blade = (
                asset.model and
                asset.model.category and
                asset.model.category.is_blade
            )
            if not is_blade:
                non_blades.append(asset)
        return non_blades

    def _get_non_blade_message(self, non_blades):
        sn_list, barcode_list = [], []
        msg_sn, msg_barcode = '', ''
        for asset in non_blades:
            if asset.sn:
                sn_list.append(asset.sn)
            elif asset.barcode:
                barcode_list.append(asset.barcode)

        if sn_list:
            msg_sn = _(
                "Assets with these sns are not blade server: {}".format(
                    ', '.join(sn_list)
                )
            )
        if barcode_list:
            msg_barcode = _(
                "Assets with these bardcodes are not blade server: {}".format(
                    ', '.join(barcode_list)
                )
            )
        return msg_sn, msg_barcode

    def post(self, request, *args, **kwargs):
        chassis_form = BladeSystemForm(request.POST)
        blade_server_formset = self.get_formset()(request.POST)

        all_data_valid = (
            chassis_form.is_valid() and
            blade_server_formset.is_valid() and
            self.validate_same_slot(blade_server_formset)
        )
        if all_data_valid:
            for form in blade_server_formset.forms:
                form.save(commit=False)
                for field in BladeSystemForm.Meta.fields:
                    setattr(
                        form.instance, field, chassis_form.cleaned_data[field]
                    )
                form.instance.save()

            msg = _(
                "Successfully changed location data for {} assets".format(
                    len(blade_server_formset.forms)
                )
            )
            messages.info(self.request, msg)
            return HttpResponseRedirect(
                reverse('asset_search', args=(self.mode,))
            )
        else:
            context = self.get_context_data(**kwargs)
            context['chassis_form'] = chassis_form
            context['blade_server_formset'] = blade_server_formset
            return self.render_to_response(context)
