# Lossless BMP Compression with Custom RLE

This project implements a lossless compression pipeline for BMP images using a custom packet-based Run-Length Encoding (RLE) algorithm.

The same input image is converted into three different BMP formats:

- **1-bit Black & White BMP**
- **4-bit Grayscale BMP**
- **8-bit Color Table BMP**

Each BMP image is then compressed using three different scan orders:

- **Row-row**
- **Column-column**
- **Zigzag (64×64 block-based)**

After compression, all encoded files are decompressed and compared with the originals to verify that the method is fully lossless.

## Method

The compression method used in this project is:

**Custom Packet-Based RLE on Packed Scan Stream**

The encoded file structure contains:

1. Original BMP header  
2. Custom RLE metadata  
3. Compressed payload  

For implementation, **Python** was used together with the **Pillow** library for image processing.

## Main Idea

The goal of this project is to analyze how:

- BMP type
- bit depth
- scan order
- and image structure

affect the performance of lossless RLE compression.

## Final Results

The final experiment showed that compression performance depends strongly on the BMP type and scan direction.

### Best result
The best compression result was obtained for:

- 1-bit Black & White BMP
- Column-column scan order

This combination achieved:

- 18.18% space saving
- Compression ratio: 1.2221
- Lossless reconstruction: TRUE

### Other results
- `bw_1bit` also produced positive compression with:
  - **13.13%** using row-row
  - **11.61%** using zigzag
- `gray_4bit` and `color_8bit` did not achieve net compression for the selected image and produced slight file size increases
- In all experiments, the decompressed files were verified to be identical to the original BMP files

## Conclusion

This project shows that RLE works best on low-bit-depth images with stronger repeated patterns.  
Among the tested scan orders, **column-column scanning** gave the best performance for the selected image, while **zigzag scanning** generally performed worse.

Even when net compression was not achieved for all formats, the method successfully demonstrated:

- correct BMP handling
- custom RLE encoding and decoding
- scan-order-based comparison
- and fully lossless reconstruction
