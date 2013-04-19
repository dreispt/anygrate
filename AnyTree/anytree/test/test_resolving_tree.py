import unittest
from AnyTree.anytree import anytree


class TestResolvingTree(unittest.TestCase):

    """ Tests """

    def setUp(self):
        super(TestResolvingTree, self).setUp()

    def test_get_ordre_import(self):

        res_country = anytree.get_ordre_importation('admin', 'admin', 'ecox_db', 'res.country',
                                                    None)
        res_account_account = anytree.get_ordre_importation('admin', 'admin', 'ecox_db',
                                                            'account.account', None)
        self.assertEquals(res_country, ['res.country'])

        self.assertEquals(res_account_account, ['account.account.type', 'res.currency',
                                                'res.country.state', 'res.country',
                                                'report.stylesheets', 'account.payment.term',
                                                'account.fiscal.position', 'res.partner.title',
                                                'product.pricelist', 'stock.journal',
                                                'res.partner.address', 'stock.location',
                                                'stock.warehouse', 'account.analytic.account',
                                                'sale.shop', 'shop.term', 'ir.actions.actions',
                                                'res.users', 'res.partner', 'res.company',
                                                'account.account'])
