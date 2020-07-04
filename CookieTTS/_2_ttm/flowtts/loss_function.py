import torch
from torch import nn
from CookieTTS.utils.model.utils import get_mask_from_lengths


class Tacotron2Loss(nn.Module):
    def __init__(self, hparams):
        super(Tacotron2Loss, self).__init__()
        self.n_group = hparams.n_group
        sigma = hparams.sigma
        self.sigma2 = sigma ** 2
        self.sigma2_2 = self.sigma2 * 2
    
    def forward(self, model_output, targets):
        mel_target, gate_target, output_lengths, *_ = targets
        mel_out, pred_output_lengths, log_s_sum, logdet_w_sum = model_output
        batch_size, n_mel_channels, frames = mel_target.shape
        
        output_lengths = output_lengths.float()
        mel_out = mel_out.float()
        log_s_sum = log_s_sum.float()
        logdet_w_sum = logdet_w_sum.float()
        
        # Length Loss
        assert not torch.isnan(output_lengths).any(), 'output_lengths has NaN values.'
        assert not torch.isnan(pred_output_lengths).any(), 'pred_output_lengths has NaN values.'
        len_pred_loss = torch.nn.MSELoss()(pred_output_lengths.log(), output_lengths.log())
        assert not torch.isnan(len_pred_loss).any(), 'len_pred_loss has NaN values.'
        
        # remove paddings before loss calc
        mask = get_mask_from_lengths(output_lengths)[:, None, :] # [B, 1, T] BoolTensor
        mask = mask.expand(mask.size(0), mel_target.size(1), mask.size(2))# [B, n_mel, T] BoolTensor
        n_elems = (output_lengths.sum() * n_mel_channels)
        #n_elems = (batch_size * n_mel_channels * frames)
        
        # Spectrogram Loss
        mel_out = torch.masked_select(mel_out, mask)
        loss_z = ((mel_out.pow(2).sum()) / self.sigma2_2)/n_elems # mean z (over all elements)
        assert not torch.isnan(loss_z).any(), 'loss_z has NaN values.'
        
        # loss_w = (logdet_W * batch_size * (T/n_group) / (T * batch_size)
        #        = ((logdet_W * batch_size) / n_group) / batch_size
        #        = logdet_W / n_group
        
        #logdet_w_sum = logdet_w_sum * (output_lengths.mean()/output_lengths.max()) # scale for padding
        #loss_w = -logdet_w_sum.sum()/(batch_size * frames * (n_mel_channels/self.n_group)) # mean logdet_w
        loss_w = -logdet_w_sum.sum()/(n_mel_channels*frames) # mean logdet_w
        assert not torch.isnan(loss_w).any(), 'loss_w has NaN values.'
        
        log_s_sum = log_s_sum.view(batch_size, -1, frames)
        log_s_sum = torch.masked_select(log_s_sum , mask[:, :log_s_sum.shape[1], :])
        loss_s = -log_s_sum.sum()/(n_elems)
        assert not torch.isnan(loss_s).any(), 'loss_s has NaN values.'
        
        #mel_out = mel_out.view(batch_size, -1)
        #logdet = logdet_w_sum + log_s_sum.view(batch_size, -1).sum((1,))
        #loss = mel_out.pow(2).sum(1) / self.sigma2_2 - logdet
        #loss /= mel_out.size(1) # average by segment length
        #loss = loss.mean() # average by batch_size
        
        loss = loss_z+loss_w+loss_s+len_pred_loss
        assert not torch.isnan(loss).any(), 'loss has NaN values.'
        
        return loss, len_pred_loss, loss_z, loss_w, loss_s