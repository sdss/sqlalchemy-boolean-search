
from __future__ import absolute_import, division, print_function

import os
from invoke import Collection, task


@task
def clean_docs(ctx):
    ''' Cleans up the docs '''
    print('Cleaning the docs')
    ctx.run("rm -rf docs/_build")


@task
def build_docs(ctx, clean=False):
    ''' Builds the Sphinx docs '''

    if clean:
        print('Cleaning the docs')
        ctx.run("rm -rf docs/_build")

    print('Building the docs')
    os.chdir('docs')
    ctx.run("make html", pty=True)


@task
def show_docs(ctx):
    """Shows the Sphinx docs"""
    print('Showing the docs')
    os.chdir('docs/_build/html')
    ctx.run('open ./index.html')


@task
def clean(ctx):
    ''' Cleans up the crap '''
    print('Cleaning')
    ctx.run("rm -rf htmlcov")
    ctx.run("rm -rf build")
    ctx.run("rm -rf dist")


@task(clean)
def deploy(ctx, repo=None):
    ''' Deploy to pypi '''
    print('Deploying to Pypi!')
    rstr = ''
    if repo:
        rstr = '-r {0}'.format(repo)
    ctx.run("python setup.py sdist bdist_wheel --universal")
    ctx.run("twine upload {0} dist/*".format(rstr))


os.chdir(os.path.dirname(__file__))

ns = Collection(clean, deploy)
docs = Collection('docs')
docs.add_task(build_docs, 'build')
docs.add_task(clean_docs, 'clean')
docs.add_task(show_docs, 'show')
ns.add_collection(docs)
