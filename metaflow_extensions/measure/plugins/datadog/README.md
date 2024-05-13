
This is Metaflow's vendored copy of [https://github.com/DataDog/datadogpy](https://github.com/DataDog/datadogpy)

## Diff

 - Dropped subpackages besides `dogstatsd` and `util`
 - Changed `import`s to be relative imports instead of global `datadog`
 - Edited the constructor to remove referneces to removed `api`
