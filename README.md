# Changes
This repo has diverged from the original fork.  It includes expanded parsing rules; see 0.1.1 changes in the CHANGELOG.  It has also been restructured as a standalone pypi package called `marvin-sqlalchemy-boolean-search`, as its
primary use is for https://github.com/sdss/marvin.  For a more general standalone package, see https://github.com/havok2063/boolean_parser, which rebuilds this repo functionality into a fully fledged python package.

This repo is maintained at https://github.com/havok2063/SQLAlchemy-boolean-search, with changes
pushed occassionally.

# SQLAlchemy-boolean-search
SQLAlchemy-boolean-search translates a boolean search string such as:

    "field1=*something* and not (field2==1 or parent.field3<=10.0)"

into its corresponding SQLAlchemy query filter:

    and_(DataModel.field1.ilike('%something%'),
         not_(or_(DataModel.field2.__eq__(2),
                  DataModel.parent.field3.__le__(10.0))))

Relationship field names such as 'parent.grandparent.name' are accepted.

The code is stable, is used in production, and enjoys a test coverage of 100%.

## Documentation
[SQLAlchemy-boolean-search documentation](http://sqlalchemy-boolean-search.readthedocs.org/)

## Authors
* Ling Thio - ling.thio [at] gmail.com

## Acknowledgements
This project would not be possible without the use of the following amazing offerings:

* [Flask](http://flask.pocoo.org/)
* [SQLAlchemy](http://www.sqlalchemy.org/)
* [pyparsing](https://pyparsing.wikispaces.com/)

## Alternative modules
* [SQLAlchemy-Searchable](https://sqlalchemy-searchable.readthedocs.org/)
  adds full text searching and relies on PostgreSQL vectors and triggers.
* [sqlalchemy-elasticquery](https://github.com/loverajoel/sqlalchemy-elasticquery)

