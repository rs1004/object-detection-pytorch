import torch
import seaborn as sns
from torchvision.ops import batched_nms
from PIL import Image, ImageFont, ImageDraw
from pathlib import Path
from tqdm import tqdm


class Inference:
    def __init__(self, model, dataloader, **cfg):
        self.model = model
        self.dataloader = dataloader

        self.__dict__.update(cfg)

    def run(self):
        colors = [tuple([int(i * 255) for i in c]) for c in sns.color_palette('hls', n_colors=len(self.dataloader.dataset.labels))]
        save_dir = Path(self.result_dir) / 'inference'
        save_dir.mkdir(exist_ok=True, parents=True)
        num_output = min(self.num_output, len(self.dataloader))

        device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
        self.model.to(device)

        count = 0
        with torch.no_grad():
            for images, _, _ in tqdm(self.dataloader, total=len(self.dataloader)):
                # to GPU device
                images = images.to(device)

                # forward
                outputs = self.model(images)

                # draw bbox and save image
                images = images.to('cpu')
                outputs = outputs.to('cpu')

                saved = []
                for i, image, output in zip(range(count, len(images) + count), images, outputs):
                    saved.append(self._draw_and_save(i, image, output, colors, save_dir))

                count += sum(saved)

                if count >= num_output:
                    break

        print('Finished Inference')

    def _draw_and_save(self, i, image, output, colors, save_dir):
        image = Image.fromarray((image.permute(1, 2, 0).numpy() * 255).astype('uint8'))

        output = output[output[:, 4].sort(descending=True).indices]

        boxes = output[:, :4]
        class_ids = output[:, 5:].max(dim=-1).indices
        confs = output[:, 4]

        # leave valid bboxes
        boxes = boxes[confs > self.conf_thresh]
        class_ids = class_ids[confs > self.conf_thresh]
        confs = confs[confs > self.conf_thresh]

        ids = batched_nms(boxes, confs, class_ids, iou_threshold=self.nms_thresh)
        boxes = boxes[ids]
        class_ids = class_ids[ids]
        confs = confs[ids]

        # draw & save
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(self.font_name, self.font_size)
        for box, conf, class_id in zip(boxes, confs, class_ids):
            xmin, ymin, xmax, ymax = box.data.numpy() * 32
            color = colors[class_id.data]
            text = f'{self.dataloader.dataset.labels[class_id.data]}: {round(float(conf.data), 3)}'

            draw.rectangle((xmin, ymin, xmax, ymax), outline=color)
            draw.text((xmin, ymin), text, fill=color, font=font)

        image.save(save_dir / f'{i+1:05}.png')

        return 1
