"""Run full cycle of data processing from download to saving dataframe."""

from kep.download.download import RemoteFile
from kep.word2csv.word import word2csv
from kep.vintage import Vintage


def run(year, month):
    #download and unpack
    remote = RemoteFile(year, month)
    remote.download()
    remote.unrar()

    # make interim csv from Word files
    word2csv(year, month)

    # parse interim csv, validate, save
    vint = Vintage(year, month)
    vint.validate()
    vint.save()


if '__main__' == __name__:
    year, month = 2017, 10

    remote = RemoteFile(year, month)
    remote.download()
    remote.unrar()

    word2csv(year, month)

    vint = Vintage(year, month)
    vint.validate()
    vint.save()

    # TODO:
    # - add sys.argv[] parameters
    # - upload method to database
