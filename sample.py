# -*- coding: utf-8 -*-

# always
from openerp.osv import fields, osv
from openerp.osv.osv import except_osv as ERPError
import logging

# often useful
from openerp import SUPERUSER_ID

# occasionally useful
import base64
import time
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, ormcache

from dbf import Date
from fnx.oe import Proposed

_logger = logging.getLogger(__name__)

COMMON_SHIPPING = (
        ('fedex_first', 'FedEx First Overnight(early AM'),
        ('fedex_next', 'FedEx Next Overnight (late AM)'),
        ('fedex_overnight', 'FedEx Standard Overnight (early PM)'),
        ('fedex_2_am', 'FedEx 2-Day AM'),
        ('fedex_2_pm', 'FedEx 2-Day PM'),
        ('fedex_3', 'FedEx 3-Day (Express Saver)'),
        ('fedex_ground', 'FedEx Ground'),
        ('ups_first', 'UPS First Overnight'),
        ('ups_next', 'UPS Next Overnight (late AM)'),
        ('ups_overnight', 'UPS Overnight (late PM)'),
        ('ups_2', 'UPS 2-Day'),
        ('ups_3', 'UPS 3-Day'),
        ('ups_ground', 'UPS Ground'),
        ('ontrac_first', 'ONTRAC First Overnight'),
        ('ontrac_next', 'ONTRAC Next Overnight (early AM)'),
        ('ontrac_overnight', 'ONTRAC Overnight (late PM)'),
        ('ontrac_2', 'ONTRACK 2-Day'),
        ('rep', 'Deliver to Sales Rep'),
        ('dhl', 'DHL (give to receptionist)'),
        )

REQUEST_SHIPPING = (
        ('cheap_1', 'Cheapest 1-Day'),
        ('cheap_2', 'Cheapest 2-Day'),
        ('cheap_3', 'Cheapest 3-Day'),
        ('cheap_ground', 'Cheapest Ground'),
        ) + COMMON_SHIPPING + (
        ('international', 'International (give to receptionist)'),
        )

shipping_urls = {
        'fedex':  'https://www.fedex.com/apps/fedextrack/?tracknumbers=%s&cntry_code=us',
        'ups':    'https://wwwapps.ups.com/WebTracking/track?track=yes&trackNums=%s',
        'ontrac': 'https://www.ontrac.com/trackingres.asp?tracking_number=%s',
        'dhl':    'http://webtrack.dhlglobalmail.com/?trackingnumber=%s',
        'usps':   'https://tools.usps.com/go/TrackConfirmAction_input?origTrackNum=%s',
        }

# custom tables
class sample_request(osv.Model):
    _name = 'sample.request'
    _inherit = ['mail.thread']
    _order = 'state, create_date'

    _track = {
        'state' : {
            'sample.mt_sample_request_new': lambda s, c, u, r, ctx: r['state'] == 'new',
            'sample.mt_sample_request_production': lambda s, c, u, r, ctx: r['state'] == 'production',
            'sample.mt_sample_request_ready': lambda s, c, u, r, ctx: r['state'] == 'shipping',
            'sample.mt_sample_request_transiting': lambda s, c, u, r, ctx: r['state'] == 'transit',
            'sample.mt_sample_request_received': lambda s, c, u, r, ctx: r['state'] == 'complete',
            }
        }

    def __init__(self, pool, cr):
        'update send_to data'
        cr.execute("UPDATE sample_request SET send_to='customer' WHERE send_to='address'")
        return super(sample_request, self).__init__(pool, cr)

    def _get_pdf(self, cr, uid, ids, field_name, arg, context=None):
        res = {}
        if isinstance(ids, (int, long)):
            ids = [ids]
        dbname = cr.dbname
        if ids:
            for id in ids:
                res[id] = '<a href="/samplerequest/%s/SampleRequest_%d.pdf">Printer Friendly</a>' % (dbname, id)
        return res

    def _get_target_date(self, cr, uid, context=None):
        today = Date.strptime(
                fields.date.context_today(self, cr, uid, context=context),
                DEFAULT_SERVER_DATE_FORMAT,
                )
        target = today.replace(delta_day=3)
        return target.strftime(DEFAULT_SERVER_DATE_FORMAT)

    def _get_tracking_url(self, cr, uid, ids, field_name, arg, context=None):
        res = {}
        if isinstance(ids, (int, long)):
            ids = [ids]
        for row in self.read(cr, uid, ids, fields=['id', 'actual_ship', 'tracking'], context=context):
            id = row['id']
            tracking_no = row['tracking']
            shipper = row['actual_ship']
            res[id] = False
            if shipper and tracking_no:
                shipper = shipper.split('_')[0]
                res[id] = '<a href="%s" target="_blank">%s</a>' % (shipping_urls[shipper] % tracking_no, tracking_no)
        return res

    _columns = {
        'state': fields.selection(
            (
                ('draft', 'Draft'),             # <- brand-spankin' new
                ('new', 'Submitted'),           # <- sales person clicked on submit
                ('production', 'Production'),   # <- julian_date_code set
                ('shipping', 'Ready to Ship'),  # <- all product_lot's filled in
                ('transit', 'In Transit'),      # <- tracking number entered
                ('complete', 'Received'),       # <- received_datetime entered
                ),
            string='Status',
            ),
        'department': fields.selection([('marketing', 'SAMMA - Marketing'), ('sales', 'SAMSA - Sales')], string='Department', required=True, track_visibility='onchange'),
        'user_id': fields.many2one('res.users', 'Request by', required=True, track_visibility='onchange'),
        'create_date': fields.datetime('Request created on', readonly=True, track_visibility='onchange'),
        'send_to': fields.selection([('rep', 'Sales Rep'), ('customer', 'Customer')], string='Send to', required=True, track_visibility='onchange'),
        'target_date_type': fields.selection([('ship', 'Ship'), ('arrive', 'Arrive')], string='Samples must', required=True, track_visibility='onchange'),
        'target_date': fields.date('Target Date', required=True, track_visibility='onchange'),
        'instructions': fields.text('Special Instructions', track_visibility='onchange'),
        'partner_id': fields.many2one('res.partner', 'Company', required=True, track_visibility='onchange'),
        'partner_is_company': fields.related('partner_id', 'is_company', type='boolean', string='Partner is Company'),
        'contact_id': fields.many2one('res.partner', 'Contact', track_visibility='onchange'),
        'contact_name': fields.related('contact_id', 'name', type='char', size=64, string='Contact Name'),
        'rep_time': fields.float("Rep's Time"),
        # fields needed for shipping
        'address': fields.text(string='Shipping Label'),
        'address_type': fields.selection([('business', 'Commercial'), ('personal', 'Residential')], string='Address type', required=True, track_visibility='onchange'),
        'ice': fields.boolean('Add ice', track_visibility='onchange'),
        'request_ship': fields.selection(REQUEST_SHIPPING, string='Ship Via', required=True, track_visibility='onchange'),
        'actual_ship': fields.selection(COMMON_SHIPPING, string='Actual Shipping Method', track_visibility='onchange'),
        'actual_ship_date': fields.date('Shipped on', track_visibility='onchange'),
        'third_party_account': fields.char('3rd Party Account Number', size=64, track_visibility='onchange'),
        'tracking': fields.char('Tracking #', size=32, track_visibility='onchange'),
        'tracking_url': fields.function(_get_tracking_url, type='char', size=256, string='Tracking #', store=False),
        'shipping_cost': fields.float('Shipping Cost', track_visibility='onchange'),
        'received_by': fields.char('Received by', size=32, track_visibility='onchange'),
        'received_datetime': fields.datetime('Received when', track_visibility='onchange'),
        # field for samples department only
        'invoice': fields.char('Invoice #', size=32, track_visibility='onchange'),
        'julian_date_code': fields.char('Julian Date Code', size=12, track_visibility='onchange'),
        'production_order': fields.char('Production Order #', size=12, track_visibility='onchange'),
        'prep_time': fields.float('Preparation Time'),
        'finish_date': fields.date('Sample Packaged Date', track_visibility='onchange'),
        # products to sample
        'product_ids': fields.one2many('sample.product', 'request_id', string='Items', track_visibility='onchange'),
        # link to printer-friendly form
        'printer_friendly': fields.function(_get_pdf, type='html', store=False),
        }

    _defaults = {
        'user_id': lambda obj, cr, uid, ctx: uid,
        'address_type': 'business',
        'state': 'draft',
        'target_date': _get_target_date,
        }

    def button_sample_submit(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'state':'new'}, context=context)

    def create(self, cr, uid, values, context=None):
        user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
        follower_ids = [u.id for u in user.company_id.sample_request_followers_ids]
        if follower_ids:
            values['message_follower_user_ids'] = follower_ids
        return super(sample_request, self).create(cr, uid, values, context=context)

    def name_get(self, cr, uid, ids, context=None):
        if isinstance(ids, (int, long)):
            ids = [ids]
        res = []
        for record in self.read(cr, uid, ids, fields=['id', 'partner_id'], context=context):
            id = record['id']
            name = (record['partner_id'] or (None, ''))[1]
            res.append((id, name))
        return res

    def _generate_order_by(self, order_spec, query):
        "correctly orders state field if state is in query"
        order_by = super(sample_request, self)._generate_order_by(order_spec, query)
        if order_spec and 'state ' in order_spec:
            state_column = self._columns['state']
            state_order = 'CASE '
            for i, state in enumerate(state_column.selection):
                state_order += "WHEN %s.state='%s' THEN %i " % (self._table, state[0], i)
            state_order += 'END '
            order_by = order_by.replace('"%s"."state" ' % self._table, state_order)
        return order_by

    def _get_address(self, cr, uid, send_to, user_id, contact_id, partner_id, context=None):
        res_partner = self.pool.get('res.partner')
        if send_to == 'rep':
            # stuff the rep's address into the record
            user = self.pool.get('res.users').browse(cr, uid, user_id, context=context)
            rep = user.partner_id
            label = rep.name + '\n' + res_partner._display_address(cr, uid, rep)
        elif send_to:
            label = False
            if contact_id:
                contact = res_partner.browse(cr, uid, contact_id, context=context)
                label = contact.name + '\n' + res_partner._display_address(cr, uid, contact)
            elif partner_id:
                partner = res_partner.browse(cr, uid, partner_id, context=context)
                label = partner.name + '\n' + res_partner._display_address(cr, uid, partner)
        else:
            label = False
        return label

    def onchange_contact_id(self, cr, uid, ids, send_to, user_id, contact_id, partner_id, context=None):
        res = {'value': {}, 'domain': {}}
        if contact_id:
            res_partner = self.pool.get('res.partner')
            contact = res_partner.browse(cr, uid, contact_id)
            if contact.is_company:
                # move into the partner_id field
                res['value']['partner_id'] = contact_id
                res['value']['contact_id'] = False
                res['domain']['contact_id'] = [('parent_id','=',contact.id)]
            elif contact.parent_id:
                # set the partner_id field with this parent
                res['value']['partner_id'] = contact.parent_id.id
                res['domain']['contact_id'] = [('parent_id','=',contact.parent_id.id)]
            else:
                # non-company person; shove value into partner
                res['value']['partner_id'] = contact.id
                res['value']['contact_id'] = False
                res['domain']['contact_id'] = []
        res['value']['address'] = self._get_address(cr, uid, send_to, user_id, contact_id, partner_id, context=context)
        return res

    def onchange_partner_id(self, cr, uid, ids, send_to, user_id, contact_id, partner_id, context=None):
        res = {'value': {}, 'domain': {}}
        if not partner_id:
            res['value']['contact_id'] = False
            res['domain']['contact_id'] = []
        else:
            res_partner = self.pool.get('res.partner')
            partner = res_partner.browse(cr, uid, partner_id)
            if contact_id:
                contact = res_partner.browse(cr, uid, contact_id)
            # if is_company: set contact domain
            # elif has parent_id: make this the contact & set contact domain
            # else: blank contact, clear domain
            if partner.is_company:
                # this is a company
                res['domain']['contact_id'] = [('parent_id','=',partner.id)]
                if contact_id and contact.parent_id.id != partner.id:
                    res['value']['contact_id'] = False
            elif partner.parent_id:
                # this is a contact at a company
                res['value']['contact_id'] = partner_id
                res['value']['partner_id'] = partner.parent_id.id
                res['domain']['contact_id'] = [('parent_id','=',partner.parent_id.id)]
            else:
                # this is a non-company person
                res['value']['contact_id'] = False
                res['domain']['contact_id'] = []

        res['value']['address'] = self._get_address(cr, uid, send_to, user_id, contact_id, partner_id, context=context)
        return res

    def onchange_send_to(self, cr, uid, ids, send_to, user_id, contact_id, partner_id, request_ship, context=None):
        res = {'value': {}, 'domain': {}}
        res['value']['address'] = self._get_address(cr, uid, send_to, user_id, contact_id, partner_id, context=context)
        if send_to == 'rep' and not request_ship:
            res['value']['request_ship'] = 'rep'
        elif request_ship == 'rep':
            res['value']['request_ship'] = False
        return res

    def onload(self, cr, uid, ids, send_to, user_id, contact_id, partner_id, context=None):
        return self.onchange_partner_id(cr, uid, ids, send_to, user_id, contact_id, partner_id, context=context)

    def unlink(self, cr, uid, ids, context=None):
        #
        # only allow if one of:
        # - uid is owner
        # - uid is manager
        # and
        # - request is Draft or Submitted (not Production, Transit, or Received)
        #
        res_users = self.pool.get('res.users')
        user = res_users.browse(cr, uid, uid, context=None)
        manager = user.has_group('base.group_sale_manager') or user.has_group('sample.group_sample_manager')
        if isinstance(ids, (int, long)):
            ids = [ids]
        for request in self.read(cr, uid, ids, fields=['user_id', 'state'], context=context):
            if request['state'] not in ('draft', 'new'):
                raise ERPError('Bad Status', 'can only delete requests that are Draft or Submitted')
            elif not manager and request['user_id'][0] != uid:
                raise ERPError('Permission Denied', 'You may only delete your own requests')
        else:
            super(sample_request, self).unlink(cr, uid, ids, context=context)

    def write(self, cr, uid, ids, values, context=None):
        if ids:
            if isinstance(ids, (int, long)):
                ids = [ids]
            user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
            for record in self.browse(cr, SUPERUSER_ID, ids, context=context):
                vals = values.copy()
                proposed = Proposed(self, cr, values, record)
                if 'state' not in vals:
                    state = 'draft' if proposed.state == 'draft' else 'new'
                    old_state = record.state
                    if proposed.julian_date_code:
                        state = 'production'
                    if proposed.product_ids:
                        for sample_product in proposed.product_ids:
                            if not sample_product.product_lot_used:
                                break
                        else:
                            state = 'shipping'
                    if proposed.finish_date:
                        state = 'shipping'
                    if proposed.tracking:
                        state = 'transit'
                    if proposed.received_datetime:
                        state = 'complete'
                    if proposed.state != state:
                        vals['state'] = state
                    if 'product_ids' in vals and old_state != 'draft':
                        if not user.has_group('sample.group_sample_user'):
                            raise ERPError('Error', 'Order has already been submitted.  Talk to someone in Samples to get more products added.')
                if proposed.state != 'draft' and not proposed.product_ids:
                    raise ERPError('Error', 'There are no products in this request.')
                super(sample_request, self).write(cr, uid, [record.id], vals, context=context)
            return True
        return super(sample_request, self).write(cr, uid, ids, values, context=context)


class sample_qty_label(osv.Model):
    _name = 'sample.qty_label'
    _order = 'common desc, name asc'

    _columns = {
        'name': fields.char('Qty Label', size=16, required=True),
        'common': fields.boolean('Commonly Used Size'),
        }


class sample_product(osv.Model):
    _name = 'sample.product'

    _columns = {
        'request_id': fields.many2one('sample.request', string='Request'),
        'qty_id': fields.many2one('sample.qty_label', string='Qty', oldname='qty'),
        'product_id': fields.many2one('product.product', string='Item', domain=[('categ_id','child_of','Saleable')]),
        'product_lot_requested': fields.char('Lot # Requested', size=24),
        'product_lot_used': fields.char('Lot # Used', size=24, oldname='product_lot'),
        'product_cost': fields.float('Retail Price'),
        }

