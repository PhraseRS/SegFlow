import os
import cv2

data_root = r"F:\data\dataset512"
img_dir = os.path.join(data_root, "JPEGImages")
sets_dir = os.path.join(data_root, "ImageSets", "Segmentation")

def clean_txt(txt_name):
    txt_path = os.path.join(sets_dir, txt_name)
    if not os.path.exists(txt_path):
        return
    with open(txt_path, 'r') as f:
        lines = f.read().splitlines()
    
    valid_lines = []
    broken_count = 0
    
    for idx, stem in enumerate(lines):
        if not stem.strip():
            continue
        # Check both .jpg and .png
        img_path_jpg = os.path.join(img_dir, stem + ".jpg")
        img_path_png = os.path.join(img_dir, stem + ".png")
        
        img_path = img_path_png if os.path.exists(img_path_png) else img_path_jpg
        
        # Try to read with cv2
        img = cv2.imread(img_path)
        if img is None:
            broken_count += 1
        else:
            valid_lines.append(stem)
    
    if broken_count > 0:
        print(f"[{txt_name}] Found and removed {broken_count} broken images!")
        with open(txt_path, 'w') as f:
            f.write("\n".join(valid_lines) + "\n")
    else:
        print(f"[{txt_name}] All images perfectly valid!")

clean_txt("train.txt")
clean_txt("val.txt")
clean_txt("test.txt")
print("Dataset cleaning completed.")
