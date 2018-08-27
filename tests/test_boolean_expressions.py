# Copyright 2015 SolidBuilds.com. All rights reserved.
#
# Authors: Ling Thio <ling.thio@gmail.com>

from __future__ import print_function
from sqlalchemy_boolean_search import parse_boolean_search
import pytest


def test_boolean_expressions():
    # Test precedence
    expression = parse_boolean_search('a=1 or b=2 or not c=3 and d=4 and e=5')
    assert repr(expression) == 'or_(a=1, b=2, and_(not_(c=3), d=4, e=5))'

    # Test parenthesis
    expression = parse_boolean_search('a=1 or not b=2 and c=3')
    assert repr(expression) == 'or_(a=1, and_(not_(b=2), c=3))'

    expression = parse_boolean_search('a=1 or not (b=2 and c=3)')
    assert repr(expression) == 'or_(a=1, not_(and_(b=2, c=3)))'

    expression = parse_boolean_search('(a=1 or not b=2) and c=3')
    assert repr(expression) == 'and_(or_(a=1, not_(b=2)), c=3)'

    # Test all operators
    expression = parse_boolean_search('a < 1 or a <= 1 or a = 1 or a == 1 or a >= 1 or a > 1 or a != 1')
    assert repr(expression) == 'or_(a<1, a<=1, a=1, a==1, a>=1, a>1, a!=1)'

    # Test example
    expression = parse_boolean_search('field1=*something* and not (field2==1 or field3<=10.0)')
    assert repr(expression) == 'and_(field1=*something*, not_(or_(field2==1, field3<=10.0)))'

    # Test range
    expr = parse_boolean_search('a >= 4 and a < 6')
    assert repr(expr) == 'and_(a>=4, a<6)'

    # Test between
    expr = parse_boolean_search('a between 1 and 2')
    assert repr(expr) == 'abetween1and2'

    expr = parse_boolean_search('a between 1 and 2 or c > 10')
    assert repr(expr) == 'or_(abetween1and2, c>10)'


def test_boolean_functions():
    # Test function expression
    expr = parse_boolean_search('func(a > 5) < 40')
    assert repr(expr) == 'func(a>5)<40'
    assert hasattr(expr, 'fxn_name')
    assert expr.fxn_name == 'func'
    assert repr(expr.condition) == 'a>5'
    assert expr.value == '40'
    assert not hasattr(expr, 'conditions')

    # Test function cone
    expr = parse_boolean_search('cone(3.4, 5.6, 1)')
    assert repr(expr) == 'cone(3.4,5.6,1)'
    assert expr.fxn_name == 'cone'
    assert expr.value == '1'
    assert expr.coords == ['3.4', '5.6']
    assert not hasattr(expr, 'conditions')


@pytest.mark.parametrize('expression',
                         [('b < 2 and func(a > 5) < 40'),
                          ('b < 2 or func(a > 5) < 40'),
                          ('b < 2 and cone(3.4, 5.6, 1)'),
                          ('b < 2 or cone(3.4, 5.6, 1)')])
def test_boolean_fxn_andor(expression):
    expr = parse_boolean_search(expression)
    assert hasattr(expr, 'conditions')
    assert hasattr(expr, 'functions')
    assert expr.conditions
    assert expr.functions
    assert len(expr.conditions) == 1
    assert len(expr.functions) == 1
    assert repr(expr.conditions[0]) == 'b<2'


def test_boolean_params():
    expr = parse_boolean_search('a < 1 and b > 2')
    assert 'a' in expr.params
    assert 'b' in expr.params
    assert sorted(['a', 'b']) == sorted(expr.uniqueparams)
    assert expr.conditions is not []


def test_condition_nobase():
    expr = parse_boolean_search('a < 1 and b > 2')
    cond = expr.conditions[0]
    assert repr(cond) == 'a<1'
    assert cond.name == 'a'
    assert cond.basename is None
    assert cond.fullname == 'a'
    assert cond.op == '<'
    assert cond.value == '1'


def test_condition_base():
    expr = parse_boolean_search('table.a < 1 and b > 2')
    cond = expr.conditions[0]
    assert repr(cond) == 'table.a<1'
    assert cond.name == 'a'
    assert cond.basename == 'table'
    assert cond.fullname == 'table.a'
    assert cond.op == '<'
    assert cond.value == '1'


@pytest.mark.parametrize('op, value, exp',
                         [('&', '64', '64'),
                          ('&', '~64', '-65'),
                          ('|', '64', '64'),
                          ('|', '~64', '-65'),
                          ('<', '~0.1', '0.1')],
                          ids=['and', 'andnot', 'or', 'ornot', 'none'])
def test_condition_bitwise(op, value, exp):
    par = 'table.a {0} {1}'.format(op, value)
    expr = parse_boolean_search(par)
    assert expr.value == exp



