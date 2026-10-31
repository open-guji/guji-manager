# guji db pull 的包装：分页改小（client.PAGE）防 500。用法同 guji db pull 的参数。
#
import sys, os
sys.path.insert(0, os.environ.get('CV', '/home/user/open-guji/open-guji-cv'))
from open_guji_cv.datastore import client as C
C.PAGE = int(os.environ.get('PAGE', '100'))
sys.argv = ['guji', 'db', 'pull', '-w', sys.argv[1]]
from open_guji_cv.cli_v2 import main
main()
