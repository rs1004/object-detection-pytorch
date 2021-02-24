import torch
import torch.nn as nn
import torch.nn.functional as F
from model.base import Model
from model.layers import Conv2dBNLeaky, Route, Reorg, Region
from torchvision.ops import box_convert, box_iou


class YoloV2(Model):
    def __init__(self, anchors, num_classes):
        super(YoloV2, self).__init__()

        self.features = nn.Sequential(
            Conv2dBNLeaky(c_in=3, c_out=32, kernel_size=3, stride=1, padding=1),
            nn.MaxPool2d(kernel_size=2, stride=2, padding=0),

            Conv2dBNLeaky(c_in=32, c_out=64, kernel_size=3, stride=1, padding=1),
            nn.MaxPool2d(kernel_size=2, stride=2, padding=0),

            Conv2dBNLeaky(c_in=64, c_out=128, kernel_size=3, stride=1, padding=1),
            Conv2dBNLeaky(c_in=128, c_out=64, kernel_size=1, stride=1),
            Conv2dBNLeaky(c_in=64, c_out=128, kernel_size=3, stride=1, padding=1),
            nn.MaxPool2d(kernel_size=2, stride=2, padding=0),

            Conv2dBNLeaky(c_in=128, c_out=256, kernel_size=3, stride=1, padding=1),
            Conv2dBNLeaky(c_in=256, c_out=128, kernel_size=1, stride=1),
            Conv2dBNLeaky(c_in=128, c_out=256, kernel_size=3, stride=1, padding=1),
            nn.MaxPool2d(kernel_size=2, stride=2, padding=0),

            Conv2dBNLeaky(c_in=256, c_out=512, kernel_size=3, stride=1, padding=1),
            Conv2dBNLeaky(c_in=512, c_out=256, kernel_size=1, stride=1),
            Conv2dBNLeaky(c_in=256, c_out=512, kernel_size=3, stride=1, padding=1),
            Conv2dBNLeaky(c_in=512, c_out=256, kernel_size=1, stride=1),
            Conv2dBNLeaky(c_in=256, c_out=512, kernel_size=3, stride=1, padding=1),
            nn.MaxPool2d(kernel_size=2, stride=2, padding=0),

            Conv2dBNLeaky(c_in=512, c_out=1024, kernel_size=3, stride=1, padding=1),
            Conv2dBNLeaky(c_in=1024, c_out=512, kernel_size=1, stride=1),
            Conv2dBNLeaky(c_in=512, c_out=1024, kernel_size=3, stride=1, padding=1),
            Conv2dBNLeaky(c_in=1024, c_out=512, kernel_size=1, stride=1),
            Conv2dBNLeaky(c_in=512, c_out=1024, kernel_size=3, stride=1, padding=1),
            Conv2dBNLeaky(c_in=1024, c_out=1024, kernel_size=3, stride=1, padding=1),
            Conv2dBNLeaky(c_in=1024, c_out=1024, kernel_size=3, stride=1, padding=1),

            Route(layers=[-9]),
            Conv2dBNLeaky(c_in=512, c_out=64, kernel_size=1, stride=1),
            Reorg(stride=2),

            Route(layers=[-1, -4]),
            Conv2dBNLeaky(c_in=1280, c_out=1024, kernel_size=3, stride=1, padding=1)
        )
        self.detector = nn.Conv2d(in_channels=1024, out_channels=len(anchors) * (5 + num_classes), kernel_size=1, stride=1)

        self.region = Region(anchors=anchors, num_classes=num_classes)

        self.route_queue = {}
        for i, m in enumerate(self.features):
            if isinstance(m, Route):
                for lnum in m.layers:
                    self.route_queue[lnum + i] = None

    def forward(self, x):
        for i, m in enumerate(self.features):
            if i in self.route_queue:
                self.route_queue[i] = m(x)
            if isinstance(m, Route):
                xs = [self.route_queue[lnum + i] for lnum in m.layers]
                x = m(xs)
            else:
                x = m(x)
        x = self.detector(x)
        out = self.region(x)
        return out

    def loss(self, outputs, gts, masks, coefs: tuple):
        l_coord, l_obj, l_noobj, l_class = coefs
        b = outputs.shape[0]
        loss_xy = loss_wh = loss_obj = loss_noobj = loss_c = 0

        for i in range(b):
            ids = torch.nonzero(masks[i]).reshape(-1)
            non_ids = torch.nonzero(1 - masks[i]).reshape(-1)

            # localization loss
            out_coords = box_convert(outputs[i, ids, 0:4], in_fmt='xyxy', out_fmt='cxcywh')
            gt_coords = box_convert(gts[i, ids, 0:4], in_fmt='xyxy', out_fmt='cxcywh')
            loss_xy = loss_xy + F.mse_loss(out_coords[:, 0:2], gt_coords[:, 0:2], reduction='sum')
            loss_wh = loss_wh + F.mse_loss(out_coords[:, 2:4].sqrt(), gt_coords[:, 2:4].sqrt(), reduction='sum')

            # confidence loss
            max_iou_i = box_iou(outputs[i, :, 0:4], gts[i, ids, 0:4]).max(dim=1).values
            loss_obj = loss_obj + F.mse_loss(max_iou_i[ids], masks[i, ids], reduction='sum')
            loss_noobj = loss_noobj + F.mse_loss(max_iou_i[non_ids], masks[i, non_ids], reduction='sum')

            # class loss
            loss_c = loss_c + F.cross_entropy(outputs[i, ids, 5:], gts[i, ids, 4].long(), reduction='sum')

        # sum up
        loss = 1/b * (l_coord * (loss_xy + loss_wh) + l_obj * loss_obj + l_noobj * loss_noobj + l_class * loss_c)
        return loss

    def get_paramaters(self):
        return self.parameters()


if __name__ == '__main__':
    model = YoloV2(
        anchors=torch.tensor([
            [1.3221, 1.73145],
            [3.19275, 4.00944],
            [5.05587, 8.09892],
            [9.47112, 4.84053],
            [11.2364, 10.0071]
        ]),
        num_classes=20
    )
    print(model)
    x = torch.rand((2, 3, 416, 416))
    print(model(x))
