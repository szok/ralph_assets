# -*- coding: utf-8 -*-
"""Forms for support module."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from collections import OrderedDict

from ajax_select.fields import AutoCompleteSelectMultipleField
from django import forms
from django.forms import ChoiceField, ModelChoiceField
from django.forms.widgets import Textarea
from django.utils.translation import ugettext_lazy as _
from django_search_forms.fields import (
    DateRangeSearchField,
    RelatedSearchField,
    TextSearchField,
)

from ralph.account.models import Region
from ralph.middleware import get_actual_regions
from ralph.ui.widgets import DateWidget

from ralph_assets import models_support
from ralph_assets.forms import LOOKUPS, ReadOnlyFieldsMixin
from ralph_assets.forms_utils import RegionRelatedSearchField, RegionSearchForm
from ralph_assets.models import AssetType
from ralph_assets.models_support import SupportType
from ralph_assets.signals import post_customize_fields as customize_fields


class SupportForm(forms.ModelForm):
    """Support add/edit form for supports."""

    class Meta:
        model = models_support.Support
        fieldset = OrderedDict([
            ('Info', [
                'asset_type', 'support_type', 'status', 'contract_id', 'name',
                'description', 'price', 'date_from', 'date_to',
                'escalation_path', 'contract_terms', 'additional_notes',
                'sla_type', 'producer', 'supplier', 'serial_no', 'invoice_no',
                'invoice_date', 'period_in_months', 'property_of', 'region',
            ]),
        ])
        widgets = {
            'date_from': DateWidget,
            'date_to': DateWidget,
            'description': Textarea(attrs={'rows': 5}),
            'escalation_path': Textarea(attrs={'rows': 5}),
            'contract_terms': Textarea(attrs={'rows': 5}),
            'additional_notes': Textarea(attrs={'rows': 5}),
            'sla_type': Textarea(attrs={'rows': 5}),
            'invoice_date': DateWidget,
        }
        fields = (
            'additional_notes',
            'asset_type',
            'contract_id',
            'contract_terms',
            'date_from',
            'date_to',
            'description',
            'escalation_path',
            'invoice_date',
            'invoice_no',
            'name',
            'period_in_months',
            'price',
            'producer',
            'property_of',
            'region',
            'serial_no',
            'sla_type',
            'status',
            'supplier',
            'support_type',
        )

    asset_type = ChoiceField(
        required=True,
        choices=[('', '----')] + [
            (choice.id, choice.name) for choice in [
                AssetType.back_office, AssetType.data_center
            ]
        ],
    )

    def clean(self, *args, **kwargs):
        result = super(SupportForm, self).clean(*args, **kwargs)
        return result

    def __init__(self, *args, **kwargs):
        super(SupportForm, self).__init__(*args, **kwargs)
        self.fields['region'] = ModelChoiceField(
            queryset=get_actual_regions(),
        )
        customize_fields.send(sender=self, mode=None)


class AddSupportForm(SupportForm):
    """Support add form for supports."""


class EditSupportForm(ReadOnlyFieldsMixin, SupportForm):
    """Support edit form for supports."""

    readonly_fields = ('created',)

    assets = AutoCompleteSelectMultipleField(
        LOOKUPS['asset_all'], required=False
    )

    class Meta(SupportForm.Meta):
        fieldset = OrderedDict([
            ('Info', [
                'asset_type', 'support_type', 'status', 'contract_id', 'name',
                'description', 'price', 'date_from', 'date_to',
                'escalation_path', 'contract_terms', 'additional_notes',
                'sla_type', 'producer', 'supplier', 'serial_no', 'invoice_no',
                'invoice_date', 'period_in_months', 'property_of', 'assets',
                'created', 'region',
            ]),
        ])
        fields = (
            'additional_notes',
            'asset_type',
            'assets',
            'contract_id',
            'contract_terms',
            'created',
            'date_from',
            'date_to',
            'description',
            'escalation_path',
            'invoice_date',
            'invoice_no',
            'name',
            'period_in_months',
            'price',
            'producer',
            'property_of',
            'region',
            'serial_no',
            'sla_type',
            'status',
            'supplier',
            'support_type',
        )


class SupportSearchForm(RegionSearchForm):
    class Meta(object):
        Model = models_support.Support
        fields = []
    support_type = RelatedSearchField(SupportType)
    contract_id = TextSearchField()
    name = TextSearchField()
    description = TextSearchField()
    date_from = DateRangeSearchField()
    date_to = DateRangeSearchField()
    additional_notes = TextSearchField()
    assets = TextSearchField(
        filter_field='assets__sn', label=_('by sn (of assigned asset)'),
    )
    region = RegionRelatedSearchField(Model=Region)
