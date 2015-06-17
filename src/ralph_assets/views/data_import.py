# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import logging

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.contrib.auth.models import User
from django.contrib.formtools.wizard.views import SessionWizardView
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import transaction
from django.db.models.fields import (
    BooleanField,
    CharField,
    DateField,
    DecimalField,
    TextField,
)
from django.db.models.fields.related import RelatedField, ManyToManyField
from django.shortcuts import render
from django.template.defaultfilters import slugify
from django.utils.dateparse import parse_date, parse_datetime
from lck.django.common.models import Named
from ralph.account.models import Region
from ralph.discovery.models_device import DeviceEnvironment, ServiceCatalog

from ralph_assets.forms_import import (
    ColumnChoiceField,
    get_model_by_name,
    get_amendment_model,
)
from ralph_assets.models_assets import (
    MODE2ASSET_TYPE,
    ASSET_TYPE2MODE,
    CreatableFromString,
    Sluggy,
    AssetType,
)
from ralph_assets.models_util import add_problem, ProblemSeverity
from ralph_assets.views.asset import AssetsBase
from ralph_assets.models import (
    Asset,
    AssetCategory,
    AssetCategoryType,
    AssetManufacturer,
    AssetModel,
)


class RequiredFieldError(Exception):
    pass


MODE2ASSET_CATEGORY_TYPE = {
    'dc': AssetCategoryType.data_center,
    'back_office': AssetCategoryType.back_office,
}

logger = logging.getLogger(__name__)


class XlsUploadView(SessionWizardView, AssetsBase):
    """The wizard view for xls/csv upload."""
    template_name = 'assets/xls_upload_wizard.html'
    file_storage = FileSystemStorage(location=settings.FILE_UPLOAD_TEMP_DIR)
    active_submodule = 'assets_import'

    @property
    def mode(self):
        """The mode of xls upload is chosen in the first step, not taken
        from url."""
        data = self.get_cleaned_data_for_step('upload')
        if data is not None:
            return ASSET_TYPE2MODE[
                AssetType.from_id(int(
                    self.get_cleaned_data_for_step('upload')['asset_type']
                ))
            ]

    @mode.setter
    def mode(self, value):
        "no-op"

    def get_form(self, step=None, data=None, files=None):
        if step is None:
            step = self.steps.current
        form = super(XlsUploadView, self).get_form(step, data, files)
        if step == 'column_choice':
            names_per_sheet, update_per_sheet, add_per_sheet =\
                self.get_cleaned_data_for_step('upload')['file']
            model = self.get_cleaned_data_for_step('upload')['model']
            form.model_reflected = model
            form.update = any(update_per_sheet.values())
            for name_list in names_per_sheet.values():
                for name in name_list:
                    form.fields[slugify(name)] = ColumnChoiceField(
                        model=model,
                        mode=self.mode,
                        label=name,
                    )
                    # set default value if name is the same as one of options
                    options = filter(
                        lambda x: x[1].lower().strip() == name.lower().strip(),
                        form.fields[slugify(name)].choices
                    )
                    if options:
                        form.fields[slugify(name)].initial = options[0][0]
        elif step == 'confirm':
            names_per_sheet, _, _ =\
                self.get_cleaned_data_for_step('upload')['file']
            mappings = {}
            all_names = set(sum((
                [slugify(n) for n in name_list]
                for name_list in names_per_sheet.values()
            ), []))
            for k, v in self.get_cleaned_data_for_step(
                'column_choice'
            ).items():
                if k in all_names and v != '':
                    mappings[k.lower()] = v
            self.storage.data['mappings'] = mappings
        return form

    def get_context_data(self, form, **kwargs):
        data = super(XlsUploadView, self).get_context_data(form, **kwargs)
        if self.steps.current == 'confirm':
            names_per_sheet, update_per_sheet, add_per_sheet =\
                self.get_cleaned_data_for_step('upload')['file']
            mappings = self.storage.data['mappings']
            all_columns = list(mappings.values())
            all_column_names = all_columns
            data_dicts = {}
            for sheet_name, sheet_data in update_per_sheet.items():
                for asset_id, asset_data in sheet_data.items():
                    data_dicts.setdefault(asset_id, {})
                    for key, value in asset_data.items():
                        data_dicts[asset_id][mappings[key.lower()]] = value
            update_table = []
            for asset_id, asset_data in data_dicts.items():
                row = [asset_id]
                for column in all_columns:
                    row.append(asset_data.get(column, ''))
                update_table.append(row)
            add_table = []
            for sheet_name, sheet_data in add_per_sheet.items():
                for asset_data in sheet_data:
                    asset_data = dict(
                        (mappings[slugify(k)], v)
                        for (k, v) in asset_data.items()
                        if slugify(k) in mappings
                    )
                    row = []
                    for column in all_columns:
                        row.append(asset_data.get(column, ''))
                    add_table.append(row)
            data['all_columns'] = all_columns
            data['all_column_names'] = all_column_names
            data['update_table'] = update_table
            data['add_table'] = add_table
        data['section'] = None
        return data

    def _get_field_value(self, field_name, value):
        """Transform a pure string into the value to be put into the field."""
        if '.' in field_name:
            Model = self.AmdModel
            _, field_name = field_name.split('.', 1)
        else:
            Model = self.Model
        field = Model._meta.get_field_by_name(field_name)[0]
        if not value:
            if isinstance(field, ManyToManyField):
                return []
            elif (
                isinstance(field, (TextField, CharField)) and
                field_name not in ('imei', 'sn', 'barcode')
            ):
                return ''
            else:
                return
        if isinstance(field, BooleanField):
            value = False if value.lower() in ["0", "false"] else True
        if isinstance(field, DecimalField):
            if value.count(',') == 1 and '.' not in value:
                value = value.replace(',', '.')
        if isinstance(field, DateField):
            value = parse_datetime(value) or parse_date(value) or None
        if field.choices:
            value_lower = value.lower().strip()
            for k, v in field.choices:
                if value_lower == v.lower().strip():
                    value = k
                    break

        if (
            isinstance(value, basestring) and
            isinstance(field, RelatedField) and
            issubclass(
                field.rel.to, (
                    Named, Named.NonUnique, User, Sluggy, DeviceEnvironment,
                    ServiceCatalog,
                )
            )

        ):
            try:
                if issubclass(field.rel.to, User):
                    value = field.rel.to.objects.get(username__iexact=value)
                elif issubclass(field.rel.to, Region):
                    try:
                        value = field.rel.to.objects.get(name__iexact=value)
                    except field.rel.to.DoesNotExist:
                        msg = 'Couldn\'t find value {!r} for key {!r}'.format(
                            value, field.name,
                        )
                        raise RequiredFieldError(msg)
                elif issubclass(field.rel.to, Sluggy):
                    value = field.rel.to.objects.get(slug=value)
                elif (
                    issubclass(field.rel.to, ServiceCatalog) or
                    issubclass(field.rel.to, DeviceEnvironment)
                ):
                    try:
                        value = field.rel.to.objects.get(name__iexact=value)
                    except field.rel.to.DoesNotExist:
                        msg = 'Couldn\'t find value {!r} for key {!r}'.format(
                            value, field.name,
                        )
                        raise RequiredFieldError(msg)
                    except MultipleObjectsReturned:
                        msg = 'Not ambiguous value {} for key {}'.format(
                            value, field.name,
                        )
                        raise RequiredFieldError(msg)
                else:
                    value = field.rel.to.objects.get(name__iexact=value)
            except field.rel.to.DoesNotExist:
                if issubclass(field.rel.to, CreatableFromString):
                    value = field.rel.to.create_from_string(
                        asset_type=MODE2ASSET_TYPE[self.mode],
                        string_name=value
                    )
                    value.save()
                else:
                    raise
        if isinstance(field, ManyToManyField):
            value = [value]
        return value

    @transaction.commit_on_success
    def done(self, form_list):
        mappings = self.storage.data['mappings']
        names_per_sheet, update_per_sheet, add_per_sheet =\
            self.get_cleaned_data_for_step('upload')['file']
        failed_assets = []
        errors = {}
        model = self.get_cleaned_data_for_step('upload')['model']
        self.Model = get_model_by_name(model)

        def get_or_create_asset_model(asset_data, asset=None):
            if model == 'ralph_assets.asset':
                category_key = [
                    k for k, v in mappings.iteritems() if v == 'model.category'
                ]
                if category_key:
                    category_name = [
                        v for k, v in asset_data.iteritems()
                        if slugify(k) == category_key[0]
                    ][0]
                    try:
                        asset_data = self.get_or_create_model(asset_data)
                    except AssetCategory.DoesNotExist:
                        msg = "Category '{0}' does not exists".format(
                            category_name
                        )
                        errors[asset or tuple(asset_data.values())] = msg
                        return asset_data, False
            return asset_data, True

        if model == 'ralph_assets.asset':
            amd_field, amd_model = get_amendment_model(self.mode)
            self.AmdModel = get_model_by_name(amd_model)
        else:
            amd_field = amd_model = self.AmdModel = None

        for sheet_name, sheet_data in update_per_sheet.items():
            for asset_id, asset_data in sheet_data.items():
                try:
                    asset = self.Model.objects.get(pk=asset_id)
                except ObjectDoesNotExist:
                    failed_assets.append(asset_id)
                    continue
                asset_data, success = get_or_create_asset_model(
                    asset_data, asset
                )
                if not success:
                    continue
                try:
                    for key, value in asset_data.items():
                        key = key.lower()
                        new_value = self._get_field_value(mappings[key], value)
                        setattr(asset, mappings[key], new_value)
                    asset.save()
                except Exception as exc:
                    errors[asset_id] = repr(exc)
        for sheet_name, sheet_data in add_per_sheet.items():
            for asset_data in sheet_data:
                asset_data, success = get_or_create_asset_model(asset_data)
                if not success:
                    continue
                not_found_messages = []
                kwargs = {}
                amd_kwargs = {}
                m2m = {}

                for key, value in asset_data.items():
                    field_name = mappings.get(slugify(key))
                    if field_name is None:
                        continue
                    try:
                        value = self._get_field_value(field_name, value)
                    except RequiredFieldError as exc:
                        errors[tuple(asset_data.values())] = repr(exc.message)
                        break
                    except ObjectDoesNotExist:
                        not_found_messages.append(
                            'Cannot find value for {}. '
                            'Resource {} not found.'.format(
                                key,
                                value,
                            )
                        )
                        value = self._get_field_value(field_name, '')

                    if amd_field and field_name.startswith(
                        amd_field + '.'
                    ):
                        _, field_name = field_name.split('.', 1)
                        amd_kwargs[field_name] = value
                    elif isinstance(value, list):
                        m2m[field_name] = value
                    else:
                        kwargs[field_name] = value
                else:
                    try:
                        if 'region' not in kwargs:
                            kwargs['region'] = Region.get_default_region()
                        asset = self.Model(**kwargs)
                        if self.AmdModel is not None:
                            amd_model_object = self.AmdModel(**amd_kwargs)
                            amd_model_object.save()
                            setattr(asset, amd_field, amd_model_object)
                        if isinstance(asset, Asset):
                            if not settings.DATA_IMPORTER['import_unmatched_assets']:  # noqa
                                asset.type = MODE2ASSET_TYPE[self.mode]
                                device = asset.find_device_to_link()
                                if not device and self.mode == 'dc':
                                    msg = (
                                        "Unable to match asset nor"
                                        "'barcode' {!r} nor sn {!r}".format(
                                            asset.barcode, asset.sn,
                                        )
                                    )
                                    raise Exception(msg)

                        else:
                            asset.asset_type = MODE2ASSET_TYPE[self.mode]
                        asset.save()
                    except Exception as exc:
                        errors[tuple(asset_data.values())] = repr(exc)
                    else:
                        for message in not_found_messages:
                            add_problem(
                                asset,
                                ProblemSeverity.correct_me,
                                message
                            )
                        for key, value in m2m.items():
                            getattr(asset, key).add(*value)
        ctx_data = self.get_context_data(None)
        ctx_data['failed_assets'] = failed_assets
        ctx_data['errors'] = errors
        return render(
            self.request,
            'assets/xls_upload_wizard_done.html',
            ctx_data
        )

    def get_or_create_model(self, data):
        """Update/add AssetModel and clear asset_data from its fields.

        Raise AssetCategory.DoesNotExist if category name is provided but not
        exists.
        """
        slugified_names = {
            slugify(k): k for k in data
        }
        mapping = {
            v: slugified_names[k]
            for k, v in self.storage.data['mappings'].iteritems()
        }
        get_name = mapping.get

        model = data.get(mapping.get('model'), None)
        category = data.pop(mapping.get('model.category'), None)
        manufacturer = data.pop(mapping.get('model.manufacturer'), None)

        if not model:
            return data

        kwargs = {'name': model, 'type': MODE2ASSET_TYPE[self.mode]}

        if category:
            category = AssetCategory.objects.get(
                name=category,
                type=MODE2ASSET_CATEGORY_TYPE[self.mode],
            )
        else:
            category = None
        kwargs['category'] = category
        if manufacturer:
            manufacturer = AssetManufacturer.objects.get_or_create(
                name=manufacturer,
            )[0]
        else:
            manufacturer = None
        kwargs['manufacturer'] = manufacturer

        data[get_name('model')] = AssetModel.objects.get_or_create(**kwargs)[0]
        return data
