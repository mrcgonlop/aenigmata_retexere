import os, sys
os.environ['TESSDATA_PREFIX'] = r'C:\Users\mrcgo\anaconda3\envs\aenigmata\share\tessdata'
sys.path.insert(0, r'C:\Users\mrcgo\Desktop\prog\proyectos\books\aenigmata_retexere')
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Users\mrcgo\anaconda3\envs\aenigmata\Library\bin\tesseract.exe'
print('tesseract:', pytesseract.get_tesseract_version())
langs = pytesseract.get_languages()
print('grc:', 'grc' in langs, '| ell:', 'ell' in langs)
from src.ocr.preprocess import preprocess
from src.ocr import recognize
print('all imports OK')
