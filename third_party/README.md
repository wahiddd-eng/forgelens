# Third-party code

## ADCD-Net

- **Paper:** K. Wong, J. Zhou, H. Wu, Y.-W. Si and J. Zhou, "ADCD-Net: Robust Document Image Forgery Localization via Adaptive DCT Feature and Hierarchical Content Disentanglement," IEEE/CVF ICCV 2025, pp. 19280–19289.
- **Repository:** https://github.com/KahimWong/ADCD-Net
- **Pinned commit:** `169d04d2d802c1d1e4d934c04c308c3e3f5c4e7a`
- **License:** MIT License

The paper calls the model ADCD-Net, while the repository is named ACDC-Net; the repository contents and README identify the project as ADCD-Net.

Never edit files inside `third_party/ADCD-Net`. Put our wrappers and changes in `src/forgelens/signals/image/`.

### Weights and data

The upstream README mentions these resources:

- [DocTamper dataset](https://github.com/qcf-568/DocTamper)
- [ADCD-Net Data (Google Drive)](https://drive.google.com/file/d/1-5BU3Bavs6SGJpaByua_FhDuUJGoo-iS/view?usp=sharing), containing `ADCDNet.pth`, `docres.pkl`, and OCR masks
- [Doc Protocol Data](https://huggingface.co/datasets/Jason37437/Doc-Protocol-Data), including `cutted_datasets_fakes.zip`
- [PaddleOCR installation](https://www.paddlepaddle.org.cn/en/install/quick?docurl=/documentation/docs/en/develop/install/pip/linux-pip_en.html) for generating OCR masks

Do not download these resources as part of setup. Any downloaded weights must be placed in `experiments/checkpoints/`, which is git-ignored.

### Dependencies

The upstream repository does not contain a requirements file. Its README documents Python 3.10.13, PyTorch 2.3.0+cu121, and albumentations 2.0.8, and requires PaddlePaddle/PaddleOCR for OCR mask generation. No requirements-file version conflicts were found with this repository's `requirements.txt`; do not change that file for the submodule.
