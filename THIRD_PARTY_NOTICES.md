# Third-party notices

The application integrates the following upstream work. Preserve upstream license files and notices when redistributing model/runtime artifacts. This list does not replace the license texts shipped in each package's `.dist-info/licenses` directory.

- TalkAI FER+ implementation: [repository](https://github.com/TalkAI/facial-emotion-recognition-gluon), MIT. Portions of preprocessing are adapted from its Microsoft FERPlus-derived `utils/image_utils.py`; retain their upstream notices.
- VinAI PhoWhisper: [repository and license](https://github.com/VinAIResearch/PhoWhisper), BSD-3-Clause. Cite Le, Nguyen and Nguyen, *PhoWhisper: Automatic Speech Recognition for Vietnamese*, ICLR 2024 Tiny Papers, when publishing research results.
- OpenCV / YuNet: [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet). See model-specific license and OpenCV library license.
- MediaPipe: [repository](https://github.com/google-ai-edge/mediapipe), Apache-2.0. Pose task weights are obtained from Google's official model registry.
- Silero VAD: [repository](https://github.com/snakers4/silero-vad), MIT.
- PyTorch, ONNX Runtime, NumPy, SciPy, FastAPI, SQLAlchemy, Next.js, React and Supabase SDK retain the license files installed with their packages.
- FFmpeg binary: supplied by `imageio-ffmpeg`; the libx264-enabled binary may have GPL obligations. Preserve the actual binary's license/build information and corresponding-source offer when distributing it. Run the bundled executable with `-L` and `-buildconf` and retain those outputs in the distribution.

Legacy MXNet is used only for model conversion and is not required by the ONNX capture runtime.
