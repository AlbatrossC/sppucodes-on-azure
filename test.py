#!/usr/bin/env python3

import cv2
import numpy as np
import sys

# More detailed symbol set from dark to light
symbols_list = list("@%#*+=-:. ")

def ascii_array_to_string(array):
    """Converts the coded image array into a single string."""
    lines = []
    for row in array:
        line = "".join(row)
        lines.append(line)
    return "\n".join(lines)

def img_to_ascii(image):
    """Converts the grayscale image to ASCII characters."""
    # resizing parameters
    height, width = image.shape
    aspect_ratio = height / width
    new_width = 150  # increase width
    new_height = int(aspect_ratio * new_width * 0.5)  # height needs adjustment

    # Resize image
    resized_image = cv2.resize(image, (new_width, new_height))

    # Normalize pixel values to fit symbols_list
    normalized = (resized_image / 255) * (len(symbols_list) - 1)
    normalized = normalized.astype(int)

    ascii_image = np.array([symbols_list[val] for val in normalized.flatten()])
    ascii_image = ascii_image.reshape(normalized.shape)
    return ascii_image

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Image Path not specified : Using sample_image.png\n")
        image_path = "IMG-20240512-WA0025.jpg"  # default image path
    else:
        print("Using {} as Image Path\n".format(sys.argv[1]))
        image_path = sys.argv[1]

    image = cv2.imread(image_path, 0)  # read image in grayscale

    ascii_art = img_to_ascii(image)
    ascii_string = ascii_array_to_string(ascii_art)

    # Save to file
    output_filename = "ascii_output_enhanced.txt"
    with open(output_filename, "w") as f:
        f.write(ascii_string)

    print(f"ASCII art saved to '{output_filename}'.")

    # Optional: print a small preview
    print("\nPreview:\n")
    print(ascii_string[:1000])  # print only the first part if it's huge
