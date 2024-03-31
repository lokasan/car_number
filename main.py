import pytesseract
import cv2
import os
import numpy as np
from PIL import Image
import io


project_path = os.path.dirname(os.path.abspath(__file__))


def detect_text(content):
    """Detects text in the file."""
    from google.cloud import vision

    client = vision.ImageAnnotatorClient()

    image = vision.Image(content=content)

    response = client.text_detection(image=image)
    texts = response.text_annotations
    print("Texts:")

    for text in texts:
        print(f'\n"{text.description}"')

        vertices = [
            f"({vertex.x},{vertex.y})" for vertex in text.bounding_poly.vertices
        ]

        print("bounds: {}".format(",".join(vertices)))

    if response.error.message:
        raise Exception(
            "{}\nFor more info on error messages, check: "
            "https://cloud.google.com/apis/design/errors".format(response.error.message)
        )


def open_img(img):
    carplate_img = Image.open(io.BytesIO(img))
    carplate_img = cv2.cvtColor(np.array(carplate_img), cv2.COLOR_BGR2RGB)

    return carplate_img


def carplate_extract(image, carplate_haar_cascade):
    carplate_rects = carplate_haar_cascade.detectMultiScale(image,
                                                            scaleFactor=1.1,
                                                            minNeighbors=50)

    x, y, w, h = carplate_rects[0]
    carplate_img = image[y + 15: y + h - 20, x + 15: x + w - 20]

    return carplate_img


def enlarge_img(image, scale_percent):
    width = int(image.shape[1] * scale_percent / 100)
    height = int(image.shape[0] * scale_percent / 100)

    dim = (width, height)
    resized_image = cv2.resize(image, dim, interpolation=cv2.INTER_AREA)

    return resized_image


def get_number_auto(image_bytes):
    carplate_img_rgb = open_img(image_bytes)

    script_dir = os.path.dirname(os.path.abspath(__file__))

    cascade_path = os.path.join(script_dir, 'haar_cascades', 'haarcascade_russian_plate_number.xml')

    carplate_haar_cascade = cv2.CascadeClassifier(cascade_path)

    carplate_extract_image = carplate_extract(carplate_img_rgb,
                                              carplate_haar_cascade)
    carplate_extract_image = enlarge_img(carplate_extract_image, 150)

    carplate_extract_image_gray = cv2.cvtColor(carplate_extract_image,
                                               cv2.COLOR_RGB2GRAY)

    # model = keras.models.load_model('emnist_letters.h5')
    # s_out = img_to_str(model, carplate_extract_image, carplate_extract_image_gray)
    # print(s_out)

    # print(detect_text(carplate_extract_image_gray))

    return "Номер автомобиля:" + "".join((pytesseract.image_to_string(
        carplate_extract_image_gray, lang='eng', config=r'--oem 1 --psm 10 -c tessedit_char_whitelist=0123456789ABCETYOPHXM'))
                                         .split()), carplate_extract_image_gray


if __name__ == "__main__":
    get_number_auto(bytes(''))
