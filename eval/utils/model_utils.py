import os
import random
from PIL import Image
import torch


def call_blip2_engine_df(sample, model, tokenizer=None):
    prompt = sample['final_input_prompt']
    img_path = sample['img_path']
    image = sample['image']
    response = model.generate({"image": image, "prompt": prompt}, max_length=5)[0]
    return response


def call_llava_engine_df(sample, model, tokenizer=None):
    from llava.constants import IMAGE_TOKEN_INDEX, DEFAULT_IMAGE_TOKEN, DEFAULT_IM_START_TOKEN, DEFAULT_IM_END_TOKEN
    from llava.conversation import conv_templates, SeparatorStyle

    def tokenizer_image_token(prompt, tokenizer, image_token_index=IMAGE_TOKEN_INDEX, return_tensors=None):
        prompt_chunks = [tokenizer(chunk).input_ids for chunk in prompt.split('<image>')]

        def insert_separator(X, sep):
            return [ele for sublist in zip(X, [sep] * len(X)) for ele in sublist][:-1]

        input_ids = []
        offset = 0
        if len(prompt_chunks) > 0 and len(prompt_chunks[0]) > 0 and prompt_chunks[0][0] == tokenizer.bos_token_id:
            offset = 1
            input_ids.append(prompt_chunks[0][0])

        for x in insert_separator(prompt_chunks, [image_token_index] * (offset + 1)):
            input_ids.extend(x[offset:])

        if return_tensors is not None:
            if return_tensors == 'pt':
                return torch.tensor(input_ids, dtype=torch.long)
            raise ValueError(f'Unsupported tensor type: {return_tensors}')
        return input_ids

    def deal_with_prompt(input_text, mm_use_im_start_end):
        qs = input_text
        if mm_use_im_start_end:
            qs = DEFAULT_IM_START_TOKEN + DEFAULT_IMAGE_TOKEN + DEFAULT_IM_END_TOKEN + '\n' + qs
        else:
            qs = DEFAULT_IMAGE_TOKEN + '\n' + qs
        return qs

    prompt = sample['final_input_prompt']
    prompt = deal_with_prompt(prompt, model.config.mm_use_im_start_end)
    conv = conv_templates['vicuna_v1'].copy()
    conv.append_message(conv.roles[0], prompt)
    conv.append_message(conv.roles[1], None)
    prompt = conv.get_prompt()
    input_ids = tokenizer_image_token(prompt, tokenizer, IMAGE_TOKEN_INDEX, return_tensors='pt').unsqueeze(0).cuda()
    image = sample['image']
    output_ids = model.generate(
        input_ids,
        images=image.unsqueeze(0).half().cuda(),
        do_sample=True,
        temperature=0.9,
        top_p=None,
        num_beams=5,
        max_new_tokens=512,
        use_cache=True)
    input_token_len = input_ids.shape[1]
    n_diff_input_output = (input_ids != output_ids[:, :input_token_len]).sum().item()
    if n_diff_input_output > 0:
        print(f'[Warning] {n_diff_input_output} output_ids are not the same as the input_ids')
    response = tokenizer.batch_decode(output_ids[:, input_token_len:], skip_special_tokens=True)[0]

    print('response:', response)
    return response




def call_QwenVL_engine_df(sample, model, tokenizer=None):
    prompt = sample['final_input_prompt']
    img = sample['img_path']
    if img:
        query = tokenizer.from_list_format([
            {'image': sample['img_path']},
            # Either a local path or an url
            {'text': prompt},
        ])
        response, history = model.chat(tokenizer, query=query, history=None)
    else:  # multiple images actually
        all_choices = sample['all_choices']
        response = random.choice(all_choices)

    print(response)
    return response

def blip_image_processor(img_path, vis_processors):
    try:
        raw_image = Image.open(img_path).convert('RGB')
    except:
        img_path = os.path.dirname(img_path)
        img_path = os.path.join(img_path, 'inf.png')
        raw_image = Image.open(img_path).convert('RGB')
    image = vis_processors["eval"](raw_image).unsqueeze(0)
    return image


def llava_image_processor(img_path, vis_processors=None):
    try:
        raw_image = Image.open(img_path).convert('RGB')
    except:
        img_path = os.path.dirname(img_path)
        img_path = os.path.join(img_path, 'inf.png')
        raw_image = Image.open(img_path).convert('RGB')
    image_tensor = vis_processors.preprocess(raw_image, return_tensors='pt')['pixel_values'][0]
    return image_tensor


