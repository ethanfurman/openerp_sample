# -*- coding: utf-8 -*-

{
    'name': 'Samples',
    'version': '0.1',
    'category': 'Generic Modules',
    'sequence': 33,
    'summary': 'Order and track product samples.',
    'description': 'Order and track product samples to existing and potential customers.',
    'author': 'Van Sebille Systems',
    'depends': [
        'base',
        'product',
        'web',
        ],
    'update_xml': [
        'sample_view.xaml',
        'security/ir.model.access.csv',
        ],                    # xml modules with data and/or views
    'installable': True,
    'application': True,
    'auto_install': False,
}
