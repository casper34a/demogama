# -*- coding: utf-8 -*-
from odoo import fields, models, api


class ResConfigSettingsGuiarQLS(models.TransientModel):
    _inherit = "res.config.settings"

    journal_indice_id = fields.Many2one('account.journal',string="Diario para indice")

    product_quote_id    = fields.Many2one('product.product',string="Producto para cuota")
    product_indice_id   = fields.Many2one('product.product',string="Producto para deuda indice")

    @api.model
    def get_values(self):
        res = super(ResConfigSettingsGuiarQLS, self).get_values()

        res['journal_indice_id'] = int(self.env['ir.config_parameter'].sudo().get_param('guiar.journal_indice_id'))
        res['product_quote_id'] = int(self.env['ir.config_parameter'].sudo().get_param('guiar.product_quote_id'))
        res['product_indice_id'] = int(self.env['ir.config_parameter'].sudo().get_param('guiar.product_indice_id'))

        return res

    @api.model
    def set_values(self):
        self.env['ir.config_parameter'].sudo().set_param('guiar.journal_indice_id', self.journal_indice_id.id)
        self.env['ir.config_parameter'].sudo().set_param('guiar.product_quote_id', self.product_quote_id.id)
        self.env['ir.config_parameter'].sudo().set_param('guiar.product_indice_id', self.product_indice_id.id)

        super(ResConfigSettingsGuiarQLS, self).set_values()