import pytest
from svdeck import meta

LINK1='https://shadowverse-wb.com/ja/deck/detail/?hash=one'
LINK2='https://shadowverse-wb.com/ja/deck/detail/?hash=two'

def table(name='核', count=40):
    return f'<table><th colspan="5">デッキレシピ</th><td width="20%" class="center"><span class="js-detail-tooltip"><img alt="{name}画像"></span><b class="a-bold">×{count}</b></td></table>'

def link(url):
    return f'<a href="{url}">コピー</a>'

def page(body):
    return '<h2 id="hl_1">デッキレシピ</h2>'+body

def test_leading_recipe_without_subheading():
    result=meta.parse_game8_deck(page(table()+link(LINK1)))
    assert result.cards==[('核',40)]
    assert (result.variant,result.anchor,result.copy_url)==('', 'hl_1', LINK1)

def test_leading_and_subheading_recipes_stay_separate():
    result=meta.parse_game8_decks(page(table('先頭')+link(LINK1)+'<h3 id="hm_1">別構築</h3>'+table('別')+link(LINK2)))
    assert [(x.cards,x.anchor,x.copy_url) for x in result]==[([('先頭',40)],'hl_1',LINK1),([('別',40)],'hm_1',LINK2)]
    with pytest.raises(ValueError,match='複数レシピ'):
        meta.parse_game8_deck(page(table()+'<h3 id="hm_1">別構築</h3>'+table('別')))

def test_prefix_without_recipe_does_not_lend_copy_link():
    result=meta.parse_game8_deck(page(link(LINK1)+'<h3 id="hm_1">構築</h3>'+table()+link(LINK2)))
    assert result.copy_url==LINK2 and result.anchor=='hm_1'

def test_next_section_recipe_and_link_are_excluded():
    result=meta.parse_game8_deck(page(table()+link(LINK1)+'<h2 id="hl_2">入替候補</h2>'+table('候補')+link(LINK2)))
    assert result.cards==[('核',40)] and result.copy_url==LINK1

def test_unidentified_subheading_stops_leading_recipe():
    result=meta.parse_game8_deck(page(table()+link(LINK1)+'<h3>入替候補</h3>'+table('候補')+link(LINK2)))
    assert result.cards==[('核',40)] and result.copy_url==LINK1

@pytest.mark.parametrize('prefix',['','<h3 id="hm_1">構築</h3>'])
def test_multiple_tables_in_one_region_are_rejected(prefix):
    with pytest.raises(ValueError,match='複数のレシピ表'):
        meta.parse_game8_decks(page(prefix+table()+table('別')))

def test_multiple_copy_links_in_leading_region_are_rejected():
    with pytest.raises(ValueError,match='複数のコピー先'):
        meta.parse_game8_decks(page(table()+link(LINK1)+link(LINK2)))

def test_nonrecipe_leading_cards_do_not_create_recipe():
    with pytest.raises(ValueError,match='独立したデッキレシピ'):
        meta.parse_game8_decks(page(table().replace('デッキレシピ','入替候補')))
