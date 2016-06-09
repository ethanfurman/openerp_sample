from collections import defaultdict, OrderedDict
import logging
import pickle

from openerp.osv import fields, osv
from openerp.osv.orm import browse_record, browse_null
from xaml import Xaml

_logger = logging.getLogger(__name__)

class wizard_sample_request_defaults(osv.TransientModel):
    _name = 'wizard.sample.request.defaults'
    _columns = {
        'user_for_default_id': fields.many2one('res.users', 'Defaults for', required=True),
        'temporary_data': fields.text('Default data to be stored in ir.values'),
        }

    def create(self, cr, uid, values, context=None):
        data = pickle.dumps(values)
        values = {'user_for_default_id': values['user_for_default_id'], 'temporary_data': data}
        return super(wizard_sample_request_defaults, self).create(cr, uid, values, context=context)

    def read(self, cr, uid, ids, fields=None, context=None, load='_classic_read'):
        records = super(wizard_sample_request_defaults, self).read(
                cr, uid, ids,
                fields=['user_for_default_id', 'temporary_data'],
                context=context, load=load,
                )
        res = []
        fields = fields or self.fields_get(cr, uid, context=context)
        for record in records:
            data = pickle.loads(record['temporary_data'])
            values = {'id': record['id']}
            for field in fields:
                if field in ('user_for_default_id', 'temporary_data'):
                    values[field] = record[field]
                    continue
                values[field] = data[field]
            res.append(values)
        return res

    def fields_view_get(self, cr, uid, view_id=None, view_type='form', context=None, toolbar=False, submenu=False):
        if view_type == 'search':
            return {
                    'arch': '<search string="wizard.sample.request.defaults"><field name="user_for_default_id" modifiers="{&quot;required&quot;: true}"/></search>',
                    'field_parent': False,
                    'model': 'wizard.sample.request.defaults',
                    'name': 'default',
                    'type': 'search',
                    'view_id': 0,
                    'fields': self.fields_get(cr, uid, context=context),
                    }
        elif view_type == 'form':
            active_id, active_ids, active_model = [context[k] for k in ['active_id', 'active_ids', 'active_model']]
            model = self.pool.get(active_model)
            fields = self.fields_get(cr, uid, context=context)
            doc = Xaml(dynamic_defaults).document
            arch = doc.string(fields=fields, order=model._user_defaultable)
            res = {
                    'name': 'sample.request.default.form',
                    'fields': fields,
                    'arch': arch,
                    'model': 'wizard.sample.request.defaults',
                    'type': 'form',
                    'view_id': 0,
                    'field_parent': False,
                    }
            return res
        return super(wizard_sample_request_defaults, self).fields_view_get(cr, uid, view_id, view_type, context, toolbar, submenu)

    def fields_get(self, cr, uid, allfields=None, context=None, write_access=True):
        # every field in the view will require two fields here:
        # - one for the actual data (so the user can change it if desired
        # - one for the type: default or skipped
        # the actual data field info we can grab from the active_model
        res = super(wizard_sample_request_defaults, self).fields_get(cr, uid, allfields, context, write_access)
        default_fields, _ = self._get_fields_and_defaults(cr, uid, allfields, context, write_access)
        res.update(default_fields)
        return res

    def _get_fields_and_defaults(self, cr, uid, allfields=None, context=None, write_access=True):
        active_id, active_ids, active_model = [context[k] for k in ['active_id', 'active_ids', 'active_model']]
        model = self.pool.get(active_model)
        model_fields = model.fields_get(cr, uid, allfields, context, write_access)
        populated_fields = {}
        populated_values = defaultdict(list)
        record = model.browse(cr, uid, active_id, context=context)
        for field in model._user_defaultable:
            if isinstance(field, tuple):
                field, subfields = field
            else:
                subfields = []
            value = record[field]
            field_spec = model_fields[field]
            if 'required' in field_spec:
                del field_spec['required']
            if isinstance(value, browse_record):
                value = value.id
            elif isinstance(value, list):
                value = [v.id for v in value]
            elif isinstance(value, browse_null):
                value = False
            populated_fields['oe_' + field] = field_spec
            populated_values['oe_' + field] = value
            # populated_values['oe_' + field].append(value)
            populated_fields['oe_default_' + field] = default_boolean
            populated_values['oe_default_' + field] = bool(value)
        return populated_fields, populated_values

    def default_get(self, cr, uid, fields_list, context=None):
        _, defaults  = self._get_fields_and_defaults(cr, uid, context=context)
        defaults['user_for_default_id'] = uid
        res = dict([(k, defaults[k]) for k in fields_list if k in defaults])
        return res

    def set_default(self, cr, uid, ids, context=None):
        # context contains 'active_id', 'active_ids', and 'active_model'
        if context is None:
            return False
        active_id, active_ids, active_model = [context[k] for k in ['active_id', 'active_ids', 'active_model']]
        model = self.pool.get(active_model)
        ir_values = self.pool.get('ir.values')
        if len(ids) > 1:
            # should never happen
            raise ValueError("Can only handle one id at a time")
        if active_id is None:
            return False
        # get memory model record with data
        record = self.browse(cr, uid, ids[0], context=context)
        data = pickle.loads(record.temporary_data)
        # extract fields that are defaults and update ir.values
        for field in model._user_defaultable:
            if isinstance(field, tuple):
                field, subfields = field
            else:
                subfields = []
            name = 'oe_' + field
            default = 'oe_default_' + field
            if not data[default]:
                continue
            if record.user_for_default_id:
                for_all_users = False
                uid = record.user_for_default_id.id
            else:
                for_all_users = True
            value = data[name]
            if subfields and value and isinstance(value[0][2], dict):
                # value: [[0, False, {'qty_id': 2, 'product_id': 33174, 'product_lot_requested': False}]]
                for op, _, d in value:
                    # d -> {'qty_id': 2, 'product_id': 33174, 'product_lot_requested': False}
                    for key in d.keys():
                        if key not in subfields:
                            del d[key]
            ir_values.set_default(
                    cr,
                    uid,
                    model=active_model,
                    field_name=field,
                    value=data[name],
                    for_all_users=for_all_users,
                    company_id=False,
                    condition=False,
                    )
        # and close window
        return {'type':'ir.actions.act_window_close'}

default_boolean = {
    'help': 'Check to include this field and its value as a default.',
    'string': 'default',
    'type': 'boolean',
    }

dynamic_defaults = '''\
~form $Default_Values version='7.0'
    ~group
        @user_for_default_id options="{'limit':15, 'create':0, 'create_edit':0}" style="{width: 50%}"
        ~hr colspan='4'
        -for field in args.order:
            -if isinstance(field, tuple):
                -name, _ = field
            -else:
                -name = field
            -if name == 'user_for_default_id':
                -continue
            -oe_name, oe_default_name = 'oe_' + name, 'oe_default_' + name
            -string = args.fields[oe_name]['string']
            -if args.fields[oe_name]['type'] in ('many2many', 'one2many'):
                ~label for=oe_name string=string
                ~field name=oe_default_name nolabel='1'
                ~separator
                ~field name=oe_name nolabel='1'
            -else:
                ~label for=name string=string
                ~div colspan='1'
                    ~field name=oe_default_name .oe_inline
                    ~field name=oe_name .oe_inline
    ~footer
        ~button @set_default $Set_Defaults .oe_highlight type='object'
        or
        ~button $Cancel special='cancel'
'''
