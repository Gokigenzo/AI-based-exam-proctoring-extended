from types import SimpleNamespace
import numpy as np
from examwatch.vision import Vision


def test_emotion_input_preserves_training_scale_and_unknown_small_face():
    class Session:
        def run(self, _, inputs):
            tensor=inputs['face']
            # Raw 0..255 input would make the softmax spuriously saturate.
            assert tensor.dtype==np.float32
            assert tensor.min()>=0 and tensor.max()<=1
            assert tensor.shape==(1,48,48,1)
            return [np.array([[.02,.02,.02,.02,.02,.02,.88]],dtype=np.float32)]
    vision=Vision.__new__(Vision)
    vision.emotion=Session()
    vision.emotion_input=SimpleNamespace(name='face')
    frame=np.full((200,300,3),220,np.uint8)
    assert np.argmax(vision.predict_emotion(frame,[30,30,100,140]))==6
    assert vision.predict_emotion(frame,[0,0,20,20]) is None
