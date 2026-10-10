"""Run the full suite and expose concise failures in GitHub check annotations."""
import unittest

if __name__=='__main__':
    suite=unittest.defaultTestLoader.discover('tests')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    for test,trace in result.errors+result.failures:
        text=trace[-2500:].replace('%','%25').replace('\r','%0D').replace('\n','%0A')
        print('::error title='+str(test).replace(',','_')+'::'+text,flush=True)
    raise SystemExit(0 if result.wasSuccessful() else 1)
