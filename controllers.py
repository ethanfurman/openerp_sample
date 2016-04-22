# -*- coding: utf-8 -*-

import openerp
import werkzeug
from openerp import SUPERUSER_ID
from openerp.addons.web import http
from openerp.addons.web.controllers.main import content_disposition
import logging
from mimetypes import guess_type
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.rl_config import defaultPageSize
from StringIO import StringIO
from antipathy import Path
from openerp.addons.fnx import Humanize

_logger = logging.getLogger(__name__)

class SampleRequest(http.Controller):

    _cp_path = '/samplerequest'

    def __getattr__(self, name):
        return self.get_file

    @http.httprequest
    def get_file(self, request):
        target_file = Path(request.httprequest.path)
        target_company = target_file.path.filename
        _logger.info('filename: %s', target_file.filename)
        _logger.info('sample id: %r', target_file.filename[14:-4])
        target_id = int(target_file.filename[14:-4])
        registry = openerp.modules.registry.RegistryManager.get(target_company)
        with registry.cursor() as cr:
            order = registry.get('sample.request').browse(cr, SUPERUSER_ID, target_id)
            file_data = self.create_pdf(Humanize(order, request.context))
            return request.make_response(
                    file_data,
                    headers=[
                        ('Content-Disposition',  content_disposition(target_file.filename, request)),
                        ('Content-Type', guess_type(target_file.filename)[0] or 'octet-stream'),
                        ('Content-Length', len(file_data)),
                        ],
                    )


    def create_pdf(self, order):
        # get data
        sales_left = self.get_sales_left(order)
        sales_right = self.get_sales_right(order)
        sample_only = self.get_sample_only(order)
        first_section = self.get_first_section(order)
        items = self.get_items(order)
        second_section = self.get_second_section(order)
        shipping_left = self.get_shipping_left(order)
        shipping_right = self.get_shipping_right(order)
        # style it
        styleSheet = getSampleStyleSheet()
        sections = []
        sections.append(Paragraph("SunRidge Farms Samples Request", styleSheet['h1']))
        sections.append(Spacer(540, 18))
        table_left = Table(sales_left, colWidths=[108, 144], rowHeights=None, style=lines)
        table_right = Table(sales_right, colWidths=[108, 144], rowHeights=None, style=lines)
        table_top = Table(
                [[table_left, '', table_right]],
                colWidths=[254, 32, 254],
                rowHeights=None,
                style=TableStyle([
                    ('BOX', (0,0), (-1,-1), 1, colors.black),
                    ('TOPPADDING', (0,0), (-1,-1), 0),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                    ('LEFTPADDING', (0,0), (-1,-1), 0),
                    ('RIGHTPADDING', (0,0), (-1,-1), 0),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('ALIGN', (-1,0), (-1,-1), 'RIGHT'),
                    ]),
                )
        sections.append(table_top)
        table_middle = Table(
                sample_only,
                colWidths=[180]*3,
                rowHeights=[24, 20],
                style=TableStyle([
                    ('BOX', (0,0), (-1,-1), 1, colors.black),
                    ('LINEBELOW', (0,0), (-1,0), 0.25, colors.black),
                    ('SPAN', (0,0), (-1,0)),
                    ('ALIGN', (0,0), (-1,0), 'CENTER'),
                    ])
                )
        sections.append(table_middle)
        sections.append(Spacer(540, 18))
        sections.append(
                Table(
                    first_section,
                    colWidths=[125, 415],
                    rowHeights=None,
                ))
        sections.append(Spacer(540, 18))
        table_bottom = Table(
                items,
                colWidths=[108, 288, 144],
                rowHeights=[20] + [30]*(len(items)-1),
                style=TableStyle([
                    ('LINEBELOW', (0,0), (-1,-1), 0.25, colors.black),
                    ])
                )
        sections.append(table_bottom)
        sections.append(Spacer(540, 18))
        sections.append(
                Table(
                    second_section,
                    colWidths=[125, 415],
                    rowHeights=[30]*2,
                ))
        sections.append(Spacer(540, 18))
        table_shipping_left = Table(
                shipping_left,
                colWidths=[108, 144],
                rowHeights=[30]*4,
                style=lines,
                )
        table_shipping_right = Table(
                shipping_right,
                colWidths=[108, 144],
                rowHeights=[60]*2,
                style=lines,
                )
        table_shipping = Table(
                [[table_shipping_left, '', table_shipping_right]],
                colWidths=[254, 32, 254],
                rowHeights=None,
                style=TableStyle([
                    ('BOX', (0,0), (-1,-1), 1, colors.black),
                    # ('INNERGRID', (0,0), (-1,-1), 0.25, colors.black),
                    ('TOPPADDING', (0,0), (-1,-1), 0),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                    ('LEFTPADDING', (0,0), (-1,-1), 0),
                    ('RIGHTPADDING', (0,0), (-1,-1), 0),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('ALIGN', (-1,0), (-1,-1), 'RIGHT'),
                    ]),
                )
        sections.append(table_shipping)
        stream = StringIO()
        SimpleDocTemplate(stream, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36, title='Sample Request').build(sections)
        return stream.getvalue()

    def get_sales_left(self, order):
        main = [
                ['Department', order.department],
                ['Request by', order.user_id.name],
                ['Created on', order.create_date],
                ['Samples Must', order.target_date_type + ' by ' + order.target_date],
                ['Send to', order.send_to],
                ]
        recip = [
                ['Recipient', '\n'.join([t for t in (order.contact_name, order.partner_id.name_get) if t])],
                ]
        return main + recip

    def get_sales_right(self, order):
        return [
                ['Ship via', order.request_ship],
                ['Address Type', order.address_type],
                ['Shipping Label', order.address],
                ['Add Ice', order.ice],
                ['3rd Party Account #', order.third_party_account],
                ]

    def get_sample_only(self, order):
        return [
                ['Samples Department Only'],
                [   'Invoice #:  %s' % order.invoice,
                    'Julian Date Code:  %s' % order.julian_date_code,
                    'Production Order #:  %s' % order.production_order,
                    ],
                ]
    def get_first_section(self, order):
        return [
                ['Special Instructions:', order.instructions],
                ]

    def get_items(self, order):
        items = [['Qty', 'Item', 'Lot #']]
        for item in order.product_ids:
            items.append([item.qty_id.name, item.product_id.name_get, item.product_lot])
        return items

    def get_second_section(self, order):
        return [
                ['Preparation Time:', order.prep_time or ''],
                ['Finished on:', order.finish_date],
                ]

    def get_shipping_left(self, order):
        return [
                ['Shipping Method:', order.actual_ship],
                ['Shipping Cost:', order.shipping_cost or ''],
                ['Shipped on:', order.actual_ship_date],
                ['Tracking #:', order.tracking],
                ]

    def get_shipping_right(self, order):
        return [
                ['Received by:', order.received_by],
                ['Received on:', order.received_datetime],
                ]


lines = TableStyle([
    ('LINEBELOW', (0,0), (-1,-1), 0.25, colors.black),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ])

