#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.filters import SimpleListFilter
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils.translation import ugettext_lazy as _
from lck.django.common.admin import ModelAdmin

from ralph import middleware
from ralph_assets import models_assets
from ralph_assets.models import (
    Asset,
    AssetCategory,
    AssetCategoryType,
    AssetManufacturer,
    AssetModel,
    AssetOwner,
    CoaOemOs,
    Licence,
    ReportOdtSource,
    ReportOdtSourceLanguage,
    Service,
    Transition,
    TransitionsHistory,
    get_edit_url,
    Warehouse,
)
from ralph_assets.models_assets import REPORT_LANGUAGES
from ralph_assets.models_dc_assets import Accessory
from ralph_assets.models_util import ImportProblem
from ralph_assets.licences.models import LicenceType, SoftwareCategory
from ralph_assets.models_support import Support, SupportType


class AssetDisabledMixin(object):

    @property
    def assets_disabled(self):
        return getattr(settings, 'ASSETS_DISABLED', False)

    def has_add_permission(self, request):
        if not self.assets_disabled:
            return super(AssetDisabledMixin, self).has_add_permission(request)
        return False

    def has_change_permission(self, request, obj=None):
        if not self.assets_disabled:
            return super(AssetDisabledMixin, self).has_change_permission(
                request, obj
            )
        return False

    def has_delete_permission(self, request, obj=None):
        if not self.assets_disabled:
            return super(AssetDisabledMixin, self).has_delete_permission(
                request, obj
            )
        return False


class SupportAdmin(AssetDisabledMixin, ModelAdmin):
    raw_id_fields = ('assets',)
    date_hierarchy = 'date_to'
    exclude = ('attachments',)
    list_display = ('name', 'contract_id',)
    list_filter = ('asset_type', 'status',)
    list_display = (
        'name',
        'contract_id',
        'date_to',
        'asset_type',
        'status',
        'support_type',
        'deleted',
    )


admin.site.register(Support, SupportAdmin)


class SupportTypeAdmin(AssetDisabledMixin, ModelAdmin):
    search_fields = ('name',)


admin.site.register(SupportType, SupportTypeAdmin)


class SoftwareCategoryAdmin(AssetDisabledMixin, ModelAdmin):
    search_fields = ('name',)
    list_display = ('name', 'asset_type',)
    list_filter = ('asset_type',)


admin.site.register(SoftwareCategory, SoftwareCategoryAdmin)


class LicenceTypeAdmin(AssetDisabledMixin, ModelAdmin):
    search_fields = ('name',)


admin.site.register(LicenceType, LicenceTypeAdmin)


class AssetOwnerAdmin(AssetDisabledMixin, ModelAdmin):
    search_fields = ('name',)


admin.site.register(AssetOwner, AssetOwnerAdmin)


class ImportProblemAdmin(AssetDisabledMixin, ModelAdmin):
    change_form_template = "assets/import_problem_change_form.html"
    list_filter = ('severity', 'content_type',)
    list_display = ('message', 'object_id', 'severity', 'content_type',)

    def change_view(self, request, object_id, extra_context=None):
        extra_context = extra_context or {}
        problem = get_object_or_404(ImportProblem, pk=object_id)
        extra_context['resource_link'] = get_edit_url(problem.resource)
        return super(ImportProblemAdmin, self).change_view(
            request,
            object_id,
            extra_context,
        )

admin.site.register(ImportProblem, ImportProblemAdmin)


class WarehouseAdmin(AssetDisabledMixin, ModelAdmin):
    save_on_top = True
    list_display = ('name',)
    search_fields = ('name',)


admin.site.register(Warehouse, WarehouseAdmin)


class BudgetInfoAdmin(AssetDisabledMixin, ModelAdmin):
    save_on_top = True
    list_display = ('name',)
    search_fields = ('name',)


admin.site.register(models_assets.BudgetInfo, BudgetInfoAdmin)


class AssetRegionFilter(SimpleListFilter):
    """
    Allow to filter assets by region
    """
    title = _('region')
    parameter_name = 'region'

    def lookups(self, request, model_admin):
        return [(r.id, r.name) for r in middleware.get_actual_regions()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(region_id=self.value())
        else:
            return queryset


class AssetAdminForm(forms.ModelForm):
    class Meta:
        model = models_assets.Asset

    def __init__(self, *args, **kwargs):
        super(AssetAdminForm, self).__init__(*args, **kwargs)
        # return only valid regions for current user
        self.fields['region'].queryset = middleware.get_actual_regions()


class AssetAdmin(AssetDisabledMixin, ModelAdmin):
    fields = (
        'sn',
        'type',
        'model',
        'status',
        'warehouse',
        'region',
        'source',
        'invoice_no',
        'order_no',
        'price',
        'support_price',
        'support_type',
        'support_period',
        'support_void_reporting',
        'provider',
        'remarks',
        'barcode',
        'request_date',
        'provider_order_date',
        'delivery_date',
        'invoice_date',
        'production_use_date',
        'production_year',
        'deleted',
    )
    search_fields = (
        'sn',
        'barcode',
        'device_info__ralph_device__id',
    )
    list_display = ('sn', 'model', 'type', 'barcode', 'status', 'deleted',)
    list_filter = ('type', AssetRegionFilter)
    form = AssetAdminForm

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Asset, AssetAdmin)


class AssetModelAdmin(AssetDisabledMixin, ModelAdmin):
    save_on_top = True
    list_display = ('name', 'type', 'category', 'show_assets_count',)
    list_filter = ('type', 'category',)
    search_fields = ('name',)

    def queryset(self, request):
        return AssetModel.objects.annotate(assets_count=Count('assets'))

    def show_assets_count(self, instance):
        return instance.assets_count
    show_assets_count.short_description = _('Assets count')
    show_assets_count.admin_order_field = 'assets_count'


admin.site.register(AssetModel, AssetModelAdmin)


class AssetCategoryAdminForm(forms.ModelForm):
    def clean(self):
        data = self.cleaned_data
        parent = self.cleaned_data.get('parent')
        type = self.cleaned_data.get('type')
        if parent and parent.type != type:
            raise ValidationError(
                _("Parent type must be the same as selected type")
            )
        return data


class AssetCategoryAdmin(AssetDisabledMixin, ModelAdmin):
    def name(self):
        type = AssetCategoryType.desc_from_id(self.type)
        if self.parent:
            name = '|-- ({}) {}'.format(type, self.name)
        else:
            name = '({}) {}'.format(type, self.name)
        return name
    form = AssetCategoryAdminForm
    save_on_top = True
    list_display = (name, 'parent', 'slug', 'type', 'code',)
    list_filter = ('type', 'is_blade',)
    search_fields = ('name',)
    prepopulated_fields = {"slug": ("type", "parent", "name",)}


admin.site.register(AssetCategory, AssetCategoryAdmin)


class AssetManufacturerAdmin(AssetDisabledMixin, ModelAdmin):
    save_on_top = True
    list_display = ('name',)
    search_fields = ('name',)


admin.site.register(AssetManufacturer, AssetManufacturerAdmin)


class ReportOdtSourceLanguageInline(admin.TabularInline):
    model = ReportOdtSourceLanguage
    extra = 0
    max_num = len(REPORT_LANGUAGES['choices'])
    fields = ('template', 'language',)


class ReportOdtSourceAdmin(AssetDisabledMixin, ModelAdmin):
    save_on_top = True
    search_fields = ('name', 'slug',)
    list_display = ('name', 'slug',)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [
        ReportOdtSourceLanguageInline,
    ]


admin.site.register(ReportOdtSource, ReportOdtSourceAdmin)


class TransitionAdmin(AssetDisabledMixin, ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ('actions',)
    list_filter = ('from_status', 'to_status', 'required_report',)
    list_display = (
        'name', 'slug', 'from_status', 'to_status', 'required_report',
    )


admin.site.register(Transition, TransitionAdmin)


class TransitionsHistoryAdmin(AssetDisabledMixin, ModelAdmin):
    list_display = ('transition', 'logged_user', 'affected_user', 'created',)
    readonly_fields = (
        'transition', 'assets', 'logged_user', 'affected_user', 'report_file',
    )

    def has_add_permission(self, request):
        return False


admin.site.register(TransitionsHistory, TransitionsHistoryAdmin)


class CoaOemOsAdmin(AssetDisabledMixin, ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


admin.site.register(CoaOemOs, CoaOemOsAdmin)


class ServiceAdmin(AssetDisabledMixin, ModelAdmin):
    list_display = ('name', 'profit_center', 'cost_center',)
    search_fields = ('name', 'profit_center', 'cost_center',)


admin.site.register(Service, ServiceAdmin)


class LicenceAdmin(AssetDisabledMixin, ModelAdmin):
    def name(self):
        return self.__unicode__()

    raw_id_fields = (
        'assets',
        'attachments',
        'manufacturer',
        'parent',
        'property_of',
        'software_category',
        'users',
    )
    search_fields = (
        'software_category__name', 'manufacturer__name', 'sn', 'niw',
    )
    list_display = (
        name, 'licence_type', 'number_bought', 'niw', 'asset_type', 'provider',
    )
    list_filter = ('licence_type', 'asset_type', 'budget_info', 'provider',)


admin.site.register(Licence, LicenceAdmin)


def _greater_than_zero_validation(value):
    if value <= 0:
        raise forms.ValidationError(_(
            'Please specify value greater than zero.',
        ))


class DataCenterForm(forms.ModelForm):

    class Meta:
        model = models_assets.DataCenter

    def clean_visualization_cols_num(self):
        data = self.cleaned_data['visualization_cols_num']
        _greater_than_zero_validation(data)
        return data

    def clean_visualization_rows_num(self):
        data = self.cleaned_data['visualization_rows_num']
        _greater_than_zero_validation(data)
        return data


class DataCenterAdmin(AssetDisabledMixin, ModelAdmin):
    form = DataCenterForm
    save_on_top = True
    list_display = ('name', 'visualization_cols_num', 'visualization_rows_num')
    search_fields = ('name',)
    fieldsets = (
        (None, {
            'fields': ('name', 'deprecated_ralph_dc'),
        }),
        (_('Visualization'), {
            'fields': ('visualization_cols_num', 'visualization_rows_num'),
        }),
    )


admin.site.register(models_assets.DataCenter, DataCenterAdmin)


class ServerRoomAdmin(AssetDisabledMixin, ModelAdmin):
    save_on_top = True
    list_display = ('name', 'data_center')
    search_fields = ('name', 'data_center__name')


admin.site.register(models_assets.ServerRoom, ServerRoomAdmin)


class RackForm(forms.ModelForm):

    class Meta:
        model = models_assets.Rack

    def clean_visualization_col(self):
        data = self.cleaned_data['visualization_col']
        _greater_than_zero_validation(data)
        return data

    def clean_visualization_row(self):
        data = self.cleaned_data['visualization_row']
        _greater_than_zero_validation(data)
        return data

    def clean(self):
        cleaned_data = super(RackForm, self).clean()
        data_center = cleaned_data.get('data_center')
        visualization_col = cleaned_data.get('visualization_col')
        visualization_row = cleaned_data.get('visualization_row')
        if not data_center or not visualization_col or not visualization_row:
            return cleaned_data
        # Check collisions.
        qs = models_assets.Rack.objects.filter(
            data_center=data_center,
            visualization_col=visualization_col,
            visualization_row=visualization_row,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        collided_racks = qs.values_list('name', flat=True)
        if collided_racks:
            raise forms.ValidationError(
                _('Selected possition collides with racks: %(racks)s.') % {
                    'racks': ' ,'.join(collided_racks),
                },
            )
        # Check dimensions.
        if data_center.visualization_cols_num < visualization_col:
            raise forms.ValidationError(
                _(
                    'Maximum allowed column number for selected data center '
                    'is %(cols_num)d.'
                ) % {
                    'cols_num': data_center.visualization_cols_num,
                },
            )
        if data_center.visualization_rows_num < visualization_row:
            raise forms.ValidationError(
                _(
                    'Maximum allowed row number for selected data center '
                    'is %(rows_num)d.'
                ) % {
                    'rows_num': data_center.visualization_rows_num,
                },
            )
        return cleaned_data


class AccessoryInline(admin.TabularInline):
    fields = ('accessory', 'position', 'remarks', 'orientation')
    model = models_assets.Rack.accessories.through
    extra = 1


class RackAdmin(AssetDisabledMixin, ModelAdmin):
    form = RackForm
    save_on_top = True
    raw_id_fields = ('deprecated_ralph_rack',)
    list_display = ('name', 'data_center', 'server_room', 'max_u_height',)
    search_fields = (
        'name', 'data_center__name', 'server_room__name', 'max_u_height',
    )
    fieldsets = (
        (None, {
            'fields': (
                'name', 'data_center', 'server_room', 'max_u_height',
                'deprecated_ralph_rack', 'description'
            ),
        }),
        (_('Visualization'), {
            'fields': (
                'visualization_col', 'visualization_row', 'orientation'
            ),
        }),
    )
    inlines = [
        AccessoryInline,
    ]


admin.site.register(models_assets.Rack, RackAdmin)


class AccessoryAdmin(AssetDisabledMixin, ModelAdmin):
    save_on_top = True
    list_display = ('name',)
    search_fields = ('name',)

admin.site.register(Accessory, AccessoryAdmin)
