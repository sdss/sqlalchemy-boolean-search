# SQLAlchemy Boolean Search Change Log

## [0.2.2] - 2021-11-19
-----------------------
- Pinning versions
  
## [0.2.1] - 2020-09-29
-----------------------
- Updating syntax for pyparsing>3 API changes.

## [0.2.0] - 2020-09-29
-----------------------
- Refactoring package structure for release on pypi

## [0.1.2] - 2020-09-28
-----------------------
- Tagging before restructure to release to pypi

## [0.1.1] - 2018-08-28
-----------------------

### Added:
- Added new parsing rules to handle general functions with args and kwargs
- Added new parsing rules to handle bitwise operators
- Added new parsing rule to handle a BETWEEN condition
- Added check on value to remove bitwise not ~ from values in regular conditions

### Changed:
- Restructured the FxnCondition into the ExprCondition
- Introduced new base FxnCondition with ConeCondition and HistCondition for parsing cone and histogram functions
