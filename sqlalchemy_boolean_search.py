# Copyright 2015 SolidBuilds.com. All rights reserved.
#
# Authors: Ling Thio <ling.thio@gmail.com>

"""
SQLAlchemy-boolean-search
=========================
SQLAlchemy-boolean-search translates a boolean search expression such as::

    field1=*something* and not (field2==1 or field3<=10.0)

into its corresponding SQLAlchemy query filter.

Install
-------

    pip install sqlalchemy-boolean-search

Usage example
-------------

    from sqlalchemy_boolean_search import parse_boolean_search

    # DataModel defined elsewhere (with field1, field2 and field3)
    from app.models import DataModel

    # Parse boolean search into a parsed expression
    boolean_search = 'field1=*something* and not (field2==1 or field3<=10.0)'
    parsed_expression = parse_boolean_search(boolean_search)

    # Retrieve records using a filter generated by the parsed expression
    records = DataModel.query.filter(parsed_expression.filter(DataModel))

Documentation
-------------
http://sqlalchemy-boolean-search.readthedocs.org/

Authors
-------
* Ling Thio - ling.thio [at] gmail.com

Revision History
--------
2016-03-5: Modified to allow for a list of ModelClasses as input - Brian Cherinka
2016-03-11: Modified to output a dictionary of parameters: values - B. Cherinka
2016-03-16: Changed sqlalchemy values in conditions to bindparam for post-replacement - B. Cherinka
2016-03-24: Allowed for = to mean equality for non string fields and LIKE for strings - B. Cherinka
          : Changed the dot relationship in get_field to filter on the relationship_name first - B. Cherinka
2016-05-11: Added support for PostgreSQL array filters, using value op ANY(array) - B. Cherinka
2016-09-12: Modified to allow for function names (with nested expression) in the expression - B. Cherinka
2016-09-12: Modified to separate out function conditions from regular conditions
2016-09-21: Modified field checks to allow for hybrid properties to pass through - B. Cherinka
2016-09-24: Added in Decimal field as an fieldtype option - B. Cherinka
2016-09-29: Modified the bindparam name to allow for value ranges of a single name - B. Cherinka
"""

from __future__ import print_function
import copy
import inspect
import decimal
import pyparsing as pp
from pyparsing import ParseException  # explicit export
from sqlalchemy import func, bindparam, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import or_, and_, not_, sqltypes, between
from operator import le, ge, gt, lt, eq, ne

__version__ = '0.2.1'

opdict = {'<=': le, '>=': ge, '>': gt, '<': lt, '!=': ne, '==': eq, '=': eq}


# Define a custom exception class
class BooleanSearchException(Exception):
    pass


# ***** Utility functions *****
def get_field(DataModelClass, field_name, base_name=None):
    """ Returns a SQLAlchemy Field from a field name such as 'name' or 'parent.name'.
        Returns None if no field exists by that field name.
    """
    # Handle hierarchical field names such as 'parent.name'
    if base_name:
        if base_name in DataModelClass.__tablename__:
            return getattr(DataModelClass, field_name, None)
        else:
            return None

    # Handle flat field names such as 'name'
    return getattr(DataModelClass, field_name, None)


# ***** Define the expression element classes *****

class FxnCondition(object):
    ''' Base function condition '''
    def __init__(self, data):
        self.data = data[0].asDict()
        self.fxn_name = self.data.get('fxn', None)
        self.args = self.data.get('args', None)
        self.kwargs = self.data.get('kwargs', None)

    def filter(self, DataModelClass):
        #return text(self.fxn_name)
        pass

    def __repr__(self):
        args = self.args if self.args else []
        kwargs = [k + '=' + g for k, g in self.kwargs.items()] if self.kwargs else []
        all_args = ','.join(args + kwargs)
        return '{0}({1})'.format(self.fxn_name, all_args)


class ConeCondition(FxnCondition):
    ''' Condition for cone searches '''
    def __init__(self, data):
        super(ConeCondition, self).__init__(data)

        if self.kwargs:
            self.coords = (self.kwargs.get('ra', None), self.kwargs.get('dec', None))
            self.value = self.kwargs.get('radius', None)
        elif self.args:
            assert len(self.args) >= 3, 'Must have at least three arguments to make a cone condition'
            coorda, coordb, value = self.args[0:3]
            self.coords = [coorda, coordb]
            self.value = value


class HistCondition(FxnCondition):
    ''' Conditon for histogram searches '''

    def __init__(self, data):
        super(HistCondition, self).__init__(data)

        if self.args:
            assert len(self.args) >= 4, 'Must have at least four arguments to make a histogram condition'
            self.parameters = self.args[:-3]
            self.n_bins, self.low_edges, self.upp_edges = self.args[-3:]


class ExprCondition(FxnCondition):
    ''' Condition for a functional condition search '''

    def __init__(self, data):
        super(ExprCondition, self).__init__(data)
        self.data = data[0].asDict()
        self.fxn_call = self.data.get('call', None)
        self.fxn_name = self.fxn_call.get('fxn', None)
        self.condition = self.fxn_call.get('condition', None)
        self.operator = self.data.get('operator', None)
        self.value = self.data.get('value', None)

    def __repr__(self):
        return '{0}({1})'.format(self.fxn_name, repr(self.condition)) + self.operator + self.value


class Condition(object):
    """ Represents a 'name operand value' condition,
        where operand can be one of: '<', '<=', '=', '==', '!=', '>=', '>'.
    """
    def __init__(self, data):
        self.data = data[0].asDict()

        self._parse_parameter_name()
        self.op = self.data.get('operator')

        self._extract_values()

        uniqueparams.append(self.fullname)
        self._bind_parameter_names()

    def _parse_parameter_name(self):
        ''' parse the parameter name into a base + name '''
        self.fullname = self.data.get('parameter')
        if '.' in self.fullname:
            self.basename, self.name = self.fullname.split('.', 1)
        else:
            self.basename = None
            self.name = self.fullname

    def _extract_values(self):
        ''' Extract the value or values from the condition '''
        self.value = self.data.get('value', None)
        if not self.value:
            if self.op == 'between':
                self.value = self._check_bitwise_value(self.data.get('value1'))
                self.value2 = self._check_bitwise_value(self.data.get('value2'))

        self.value = self._check_bitwise_value(self.value)

    def _check_bitwise_value(self, value):
        ''' check if value has a bitwise ~ in it

        Removes any bitwise ~ found in a value for a condition.
        If the operand is a bitwise & or |, convert the ~value to its
        integer appropriate.  E.g. ~64 -> -65.

        Parameters:
            value (str): A string numerical value

        Returns:
            The str value or value converted to the proper bitwise negative
        '''

        if '~' in value:
            value = value.replace('~', '')
            if self.op in ['&', '|']:
                value = str(-1 * (int(value)) - 1)

        return value

    def _bind_parameter_names(self):
        ''' Bind the parameters names to the values '''

        if self.fullname not in params:
            params.update({self.fullname: self.value})
            self.bindname = self.fullname
        else:
            count = list(params.keys()).count(self.fullname)
            self.bindname = '{0}_{1}'.format(self.fullname, count)
            params.update({self.fullname: self.value})

    def filter(self, DataModelClass):
        ''' Return the condition as an SQLalchemy query condition '''

        condition = None
        if inspect.ismodule(DataModelClass):
            # one module
            models = [i[1] for i in inspect.getmembers(DataModelClass, inspect.isclass) if hasattr(i[1], '__tablename__')]
        else:
            # list of Model Classes
            if isinstance(DataModelClass, list):
                models = DataModelClass
            else:
                models = None

        if models:
            # Input is a a list of DataModelClasses
            field = None
            index = None
            for i, model in enumerate(models):

                field = get_field(model, self.name, base_name=self.basename)
                try:
                    ptype = field.type
                    ilike = field.ilike
                except AttributeError as e:
                    ptype = None
                    ilike = None

                if not isinstance(field, type(None)) and ptype and ilike:
                    index = i
                    break

            if isinstance(field, type(None)):
                raise BooleanSearchException(
                    "Table '%(table_name)s' does not have a field named '%(field_name)s'."
                    % dict(table_name=model.__tablename__, field_name=self.name))

            condition = self.filter_one(models[index], field=field, condition=condition)

        else:
            # Input is only one DataModelClass
            field = get_field(DataModelClass, self.name)
            if field:
                condition = self.filter_one(DataModelClass, field=field, condition=condition)
            else:
                raise BooleanSearchException(
                    "Table '%(table_name)s' does not have a field named '%(field_name)s'."
                    % dict(table_name=DataModelClass.__tablename__, field_name=self.name))

        return condition

    def format_value(self, value, fieldtype, field):
        ''' Formats the value based on the fieldtype '''

        if fieldtype == float or fieldtype == decimal.Decimal:
            try:
                outvalue = float(value)
                lower_field = field
            except:
                raise BooleanSearchException(
                    "Field {0} expects a float value. Received value {1} instead.".format(self.name, value))
        elif fieldtype == int:
            try:
                outvalue = int(value)
                lower_field = field
            except:
                raise BooleanSearchException(
                    "Field {0} expects an integer value. Received value {1} instead.".format(self.name, value))
        else:
            lower_field = func.lower(field)
            outvalue = value

        return outvalue, lower_field

    def bindAndLowerValue(self, field):
        '''Bind and lower the value based on field type '''

        lower_value_2 = None
        # get python field type
        ftypes = [float, int, decimal.Decimal]
        fieldtype = field.type.python_type

        value, lower_field = self.format_value(self.value, fieldtype, field)
        if hasattr(self, 'value2'):
            value2, lower_field = self.format_value(self.value2, fieldtype, field)

        # Bind the parameter value to the parameter name
        boundvalue = bindparam(self.bindname, value)
        lower_value = func.lower(boundvalue) if fieldtype not in ftypes else boundvalue
        if hasattr(self, 'value2'):
            self.bindname = '{0}_{1}'.format(self.fullname, 2)
            boundvalue2 = bindparam(self.bindname, value2)
            lower_value_2 = func.lower(boundvalue2) if fieldtype not in ftypes else boundvalue2

        return lower_field, lower_value, lower_value_2

    def filter_one(self, DataModelClass, field=None, condition=None):
        """ Return the condition as a SQLAlchemy query condition
        """
        if not isinstance(field, type(None)):
            # Prepare field and value
            lower_field, lower_value, lower_value_2 = self.bindAndLowerValue(field)

            # Handle Arrays
            if isinstance(field.type, postgresql.ARRAY):
                condition = field.any(self.value, operator=opdict[self.op])
            else:
                # Do Normal Scalar Stuff

                # Return SQLAlchemy condition based on operator value
                # self.name is parameter name, lower_field is Table.parameterName
                if self.op == '==':
                    condition = lower_field.__eq__(lower_value)
                elif self.op == '<':
                    condition = lower_field.__lt__(lower_value)
                elif self.op == '<=':
                    condition = lower_field.__le__(lower_value)
                elif self.op == '>':
                    condition = lower_field.__gt__(lower_value)
                elif self.op == '>=':
                    condition = lower_field.__ge__(lower_value)
                elif self.op == '!=':
                    condition = lower_field.__ne__(lower_value)
                elif self.op == '=':
                    if isinstance(field.type, sqltypes.TEXT) or \
                       isinstance(field.type, sqltypes.VARCHAR) or \
                       isinstance(field.type, sqltypes.String):
                        # this operator maps to LIKE
                        # x=5 -> x LIKE '%5%' (x contains 5)
                        # x=5* -> x LIKE '5%' (x starts with 5)
                        # x=*5 -> x LIKE '%5' (x ends with 5)
                        field = getattr(DataModelClass, self.name)
                        value = self.value
                        if value.find('*') >= 0:
                            value = value.replace('*', '%')
                            condition = field.ilike(bindparam(self.bindname, value))
                        else:
                            condition = field.ilike('%' + bindparam(self.bindname, value) + '%')
                    else:
                        # if not a text column, then use "=" as a straight equals
                        condition = lower_field.__eq__(lower_value)
                elif self.op == 'between':
                    # between condition
                    condition = between(lower_field, lower_value, lower_value_2)
                elif self.op in ['&', '|']:
                    # bitwise operations
                    condition = lower_field.op(self.op)(lower_value) > 0

        return condition

    def __repr__(self):
        more = 'and' + self.value2 if hasattr(self, 'value2') else ''
        return self.fullname + self.op + self.value + more


def update_params(condition):
    ''' update the global params list with parameter/value '''
    if isinstance(condition, Condition) and condition.name not in params:
        params.update({condition.fullname: condition.value})


class BoolNot(object):
    """ Represents the boolean operator NOT
    """
    def __init__(self, data):
        self.condition = data[0][1]
        update_params(self.condition)

    def filter(self, DataModelClass):
        """ Return the operator as a SQLAlchemy not_() condition
        """
        if not isinstance(self.condition, FxnCondition):
            return not_(self.condition.filter(DataModelClass))

    def __repr__(self):
        return 'not_(' + repr(self.condition) + ')'


class BoolAnd(object):
    """ Represents the boolean operator AND
    """
    def __init__(self, data):
        self.conditions = []
        for condition in data[0]:
            if condition and condition != 'and':
                if isinstance(condition, FxnCondition):
                    functions.append(condition)
                else:
                    self.conditions.append(condition)
                #self.conditions.append(condition)
                update_params(condition)

    def filter(self, DataModelClass):
        """ Return the operator as a SQLAlchemy and_() condition
        """
        # conditions = [condition.filter(DataModelClass) for condition in self.conditions
        #               if not isinstance(condition, (FxnCondition, ConeCondition))]
        conditions = [condition.filter(DataModelClass) for condition in self.conditions]
        return and_(*conditions)  # * converts list to argument sequence

    def removeFunctions(self):
        ''' remove the fxn conditions '''
        self.conditions = [condition for condition in self.conditions
                           if not isinstance(condition, FxnCondition)]

    def __repr__(self):
        return 'and_(' + ', '.join([repr(condition) for condition in self.conditions]) + ')'


class BoolOr(object):
    """ Represents the boolean operator OR
    """
    def __init__(self, data):
        self.conditions = []
        for condition in data[0]:
            if condition and condition != 'or':
                if isinstance(condition, FxnCondition):
                    functions.append(condition)
                else:
                    self.conditions.append(condition)
                update_params(condition)

    def filter(self, DataModelClass):
        """ Return the operator as a SQLAlchemy or_() condition
        """
        conditions = [condition.filter(DataModelClass) for condition in self.conditions if not isinstance(condition, FxnCondition)]
        return or_(*conditions)  # * converts list to argument sequence

    def __repr__(self):
        return 'or_(' + ', '.join([repr(condition) for condition in self.conditions]) + ')'

    def removeFunctions(self):
        ''' remove the fxn conditions '''
        self.conditions = [condition for condition in self.conditions if not isinstance(condition, FxnCondition)]

# ***** Define the boolean condition expressions *****

# Define expression elements
LPAR = pp.Suppress('(')
RPAR = pp.Suppress(')')
number = pp.Regex(r"[+-~]?\d+(:?\.\d*)?(:?[eE][+-]?\d+)?")
name = pp.Word(pp.alphas + '._', pp.alphanums + '._').setResultsName('parameter')
#operator = pp.Regex("==|!=|<=|>=|<|>|=|&|~|||").setResultsName('operator')
operator = pp.oneOf(['==', '<=', '<', '>', '>=', '=', '!=', '&', '|']).setResultsName('operator')
value = (pp.Word(pp.alphanums + '-_.*') | pp.QuotedString('"') | number).setResultsName('value')

# list of numbers
nl = pp.delimitedList(number, combine=True)
narr = pp.Combine('[' + nl + ']')

# function arguments
arglist = pp.delimitedList(number | (pp.Word(pp.alphanums + '-_') + pp.NotAny('=')) | narr)
args = pp.Group(arglist).setResultsName('args')
# function keyword arguments
key = pp.Word(pp.alphas) + pp.Suppress('=')
values = (number | pp.Word(pp.alphas))
keyval = pp.dictOf(key, values)
kwarglist = pp.delimitedList(keyval)
kwargs = pp.Group(kwarglist).setResultsName('kwargs')
# build generic function
fxn_args = pp.Optional(args) + pp.Optional(kwargs)
fxn_name = (pp.Word(pp.alphas)).setResultsName('fxn')
fxn = pp.Group(fxn_name + LPAR + fxn_args + RPAR)

# overall (recursvie) where clause
whereexp = pp.Forward()

# condition
condition = pp.Group(name + operator + value).setResultsName('condition')
condition.setParseAction(Condition)

# between condition
between_cond = pp.Group(name + pp.CaselessLiteral('between').setResultsName('operator') +
                        value.setResultsName('value1') + pp.CaselessLiteral('and') +
                        value.setResultsName('value2'))
between_cond.setParseAction(Condition)

# fxn expression condition
function_call = pp.Group(fxn_name + LPAR + condition + RPAR).setResultsName('call')
fxn_cond = pp.Group(function_call + operator + value)
fxn_cond.setParseAction(ExprCondition)

# cone fxn conditions
cone_cond = copy.copy(fxn)
cone_cond.setParseAction(ConeCondition)

# histogram fxn conditions
hist_cond = copy.copy(fxn)
hist_cond.setParseAction(HistCondition)

# combine all conditions together
wherecond = condition | fxn_cond | between_cond | cone_cond | hist_cond
whereexp <<= wherecond

# Define the expression as a hierarchy of boolean operators
# with the following precedence: NOT > AND > OR
expression_parser = pp.infixNotation(whereexp, [
    (pp.CaselessLiteral("not"), 1, pp.opAssoc.RIGHT, BoolNot),
    (pp.CaselessLiteral("and"), 2, pp.opAssoc.LEFT, BoolAnd),
    (pp.CaselessLiteral("or"), 2, pp.opAssoc.LEFT, BoolOr),
])

params = {}
uniqueparams = []
functions = []


def parse_boolean_search(boolean_search):
    """ Parses the boolean search expression into a hierarchy of boolean operators.
        Returns a BoolNot or BoolAnd or BoolOr object.
    """
    global params, functions, uniqueparams
    params = {}
    uniqueparams = []
    functions = []
    try:
        expression = expression_parser.parseString(boolean_search)[0]
    except ParseException as e:
        raise BooleanSearchException("Parsing syntax error ({0}) at line:{1}, "
            "col:{2}".format(e.markInputline(), e.lineno, e.col))
    else:
        expression.params = params
        expression.uniqueparams = list(set(uniqueparams))
        expression.functions = functions
        return expression


